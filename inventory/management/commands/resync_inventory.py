"""
Management command: resync_inventory
======================================
Complete data integrity recovery tool.  Designed to be run after ANY
force-change made via Django Admin, direct DB edits, or shell commands.

Handles:
  - Deleted documents → orphaned StockMoves cleaned up
  - Deleted document lines → excess StockMoves removed
  - Changed quantities on lines → StockMoves corrected
  - Changed document status (un-posted, re-posted) → balances rebuilt
  - Duplicate StockMoves → deduplicated
  - Missing StockMoves → backfilled from document lines
  - Missing unit conversions → hard error, aborts the ENTIRE Phase 0-2 run
    atomically (no silent fallback, no partial commit)
  - SO bundle components missing from DN/PU → backfilled
  - Financial statements → recalculated after inventory changes

Phases:
  Phase 0 — Clean StockMoves
    0a: Delete orphaned moves (source document deleted in admin)
    0b: Deduplicate moves (same doc+item+location appears multiple times)
    0c: Delete excess moves (document line deleted but move remains)

  Phase 1 — Fix StockMove quantities
    Recalculate qty from source document lines with correct unit conversion.
    Backfill missing moves for document lines that have no StockMove.

  Phase 2 — Rebuild StockBalance from scratch
    Ignores existing balances.  Walks every POSTED document chronologically,
    converts each line to inventory unit, accumulates (item, location) → qty.

  Phase 3 — Data integrity audit
    Reports negative balances, remaining duplicates, missing conversions.

  Phase 4 — Recalculate financial statements
    Rebuilds MonthlyCashflowSummary for all months with data.

  Phase 5 — Create audit log
    Records what the resync changed in the ManualLog table.

Usage:
    python manage.py resync_inventory                  # full run (all phases)
    python manage.py resync_inventory --dry-run        # preview without saving
    python manage.py resync_inventory --phase 2        # just rebuild balances
    python manage.py resync_inventory --quiet          # suppress per-row output
"""
from collections import defaultdict
from contextlib import ExitStack
from decimal import Decimal, InvalidOperation

from django.core.management.base import BaseCommand, CommandError
from django.db import connections, transaction
from django.utils import timezone

from catalog.models import convert_to_base_unit
from core.models import DocumentStatus
from inventory.models import StockBalance, StockMove, MoveStatus, MoveType


# ── helpers ─────────────────────────────────────────────────────────────────

def _inventory_unit(item):
    """Return the canonical unit for inventory rebuilding.

    Uses item.default_unit (the procurement/base unit) for all inventory
    tracking. This is the unit in which StockMoves and StockBalances are
    stored, regardless of selling_unit configuration.
    """
    return item.default_unit


class ConversionError:
    """Record of a failed unit conversion — collected during a resync run."""
    __slots__ = ('item_code', 'from_unit', 'to_unit', 'label', 'message')

    def __init__(self, item_code, from_unit, to_unit, label, message):
        self.item_code = item_code
        self.from_unit = from_unit
        self.to_unit = to_unit
        self.label = label
        self.message = message

    def __str__(self):
        return (
            f'{self.item_code}: {self.from_unit} → {self.to_unit}  '
            f'({self.label})  —  {self.message}'
        )

    @property
    def key(self):
        """De-duplication key: one entry per (item, from_unit, to_unit)."""
        return (self.item_code, self.from_unit, self.to_unit)


# Module-level list — populated by _safe_convert, checked before commit.
_conversion_errors: list[ConversionError] = []


def _all_manager(model):
    """Return the unfiltered manager for a model.

    Models that inherit from SoftDeleteModel have an ``all_objects`` manager
    that bypasses the ``is_active=True`` filter.  The resync command must use
    this manager so that soft-deleted but POSTED documents are still counted
    — otherwise Phase 0 would delete their StockMoves as "orphaned" and
    Phase 2 would omit their quantities, leading to incorrect (often
    negative) balances.

    Models without soft-delete (POSSale, POSRefund, CustomerService) just
    use the default ``objects`` manager.
    """
    return getattr(model, 'all_objects', model.objects)


def _safe_convert(qty, from_unit, to_unit, label, warn_fn, item=None):
    """Convert qty between units.  Raises on failure instead of falling back.

    When from_unit == to_unit the conversion is trivially correct.
    Otherwise, delegates to convert_to_base_unit() which looks up a
    UnitConversion record.  If none exists the error is recorded in
    _conversion_errors and re-raised so the caller can decide whether
    to abort immediately or collect all errors first.
    """
    try:
        return convert_to_base_unit(qty, from_unit, to_unit, item=item)
    except (ValueError, Exception) as exc:
        from_label = getattr(from_unit, 'abbreviation', str(from_unit))
        to_label = getattr(to_unit, 'abbreviation', str(to_unit)) if to_unit is not None else 'N/A'
        item_code = getattr(item, 'code', '?') if item else '?'

        err = ConversionError(
            item_code=item_code,
            from_unit=from_label,
            to_unit=to_label,
            label=label,
            message=str(exc),
        )
        _conversion_errors.append(err)
        raise


# ── Phase 0 helpers ─────────────────────────────────────────────────────────

def _deduplicate_moves(dry_run, warn_fn):
    """
    Remove duplicate POSTED StockMoves whose (reference_type, reference_id,
    item_id, from_location_id, to_location_id) tuple appears more than once.
    For each group keep the move with qty closest to the converted source-doc
    qty; when undecidable keep the oldest (lowest pk) and delete the rest.
    Also removes "phantom" duplicates — a past bug in the backfill created
    moves with NULL from/to locations alongside real moves with concrete
    locations for the same (ref_type, ref_id, item). The NULL-location ghost
    is deleted so real inventory impact is preserved.
    Returns (removed_count, groups_count).
    """
    from django.db.models import Count

    dupes = list(
        StockMove.objects
        .filter(status=MoveStatus.POSTED)
        .exclude(reference_number__startswith='REV-')
        .exclude(reference_number__startswith='VOID-')
        .values('reference_type', 'reference_id', 'item_id',
                'from_location_id', 'to_location_id', 'batch_number', 'serial_number')
        .annotate(cnt=Count('id'))
        .filter(cnt__gt=1)
    )

    removed = 0
    for grp in dupes:
        moves = list(
            StockMove.objects.filter(
                reference_type=grp['reference_type'],
                reference_id=grp['reference_id'],
                item_id=grp['item_id'],
                from_location_id=grp['from_location_id'],
                to_location_id=grp['to_location_id'],
                batch_number=grp['batch_number'],
                serial_number=grp['serial_number'],
                status=MoveStatus.POSTED,
            ).exclude(reference_number__startswith='REV-')
             .exclude(reference_number__startswith='VOID-')
             .order_by('id')
             .select_related('item__default_unit', 'item__selling_unit', 'unit')
        )
        if len(moves) < 2:
            continue
        # Keep the first (oldest); delete the rest
        to_delete = moves[1:]
        for m in to_delete:
            warn_fn(
                f'    [DEDUP] Removing duplicate Move#{m.pk} '
                f'ref={m.reference_type}#{m.reference_id} '
                f'item={m.item.code} qty={m.qty}'
            )
            if not dry_run:
                m.delete()
            removed += 1

    # ── Phantom NULL-location cleanup ───────────────────────────────────────
    # Groups keyed only on (ref_type, ref_id, item_id). When one move in the
    # group has both from_location and to_location NULL AND another move has a
    # concrete location, the NULL move is a backfill phantom produced by the
    # pre-fix bug.  Delete the phantom, keep the real ones.
    phantom_removed, phantom_groups = _remove_phantom_null_location_moves(dry_run, warn_fn)
    return removed + phantom_removed, len(dupes) + phantom_groups


def _remove_phantom_null_location_moves(dry_run, warn_fn):
    """Delete moves with NULL from/to location when a concrete-location move
    exists for the same (ref_type, ref_id, item).  Returns (removed, groups)."""
    from django.db.models import Count, Q

    loose_keys = list(
        StockMove.objects
        .filter(status=MoveStatus.POSTED)
        .exclude(reference_number__startswith='REV-')
        .exclude(reference_number__startswith='VOID-')
        .values('reference_type', 'reference_id', 'item_id')
        .annotate(cnt=Count('id'))
        .filter(cnt__gt=1)
    )

    removed = 0
    groups = 0
    for key in loose_keys:
        moves = list(
            StockMove.objects.filter(
                reference_type=key['reference_type'],
                reference_id=key['reference_id'],
                item_id=key['item_id'],
                status=MoveStatus.POSTED,
            )
            .exclude(reference_number__startswith='REV-')
            .exclude(reference_number__startswith='VOID-')
            .order_by('id')
            .select_related('item')
        )
        if len(moves) < 2:
            continue
        null_loc = [m for m in moves if m.from_location_id is None and m.to_location_id is None]
        has_loc = [m for m in moves if m.from_location_id is not None or m.to_location_id is not None]
        if not null_loc or not has_loc:
            continue
        groups += 1
        for m in null_loc:
            warn_fn(
                f'    [PHANTOM] Removing NULL-location Move#{m.pk} '
                f'ref={m.reference_type}#{m.reference_id} '
                f'item={m.item.code} qty={m.qty} '
                f'(real move exists with concrete location)'
            )
            if not dry_run:
                m.delete()
            removed += 1
    return removed, groups


def _delete_orphaned_moves(dry_run, warn_fn, info_fn):
    """
    Delete POSTED StockMoves whose source document no longer exists in the DB.

    For each known reference_type, collects all reference_ids present in
    StockMove, then queries the corresponding model to find which IDs are
    missing.  Any StockMove pointing to a missing document is an orphan and
    is deleted so that Phase 2 balance recalculation isn't corrupted by
    moves that were never reversed when their document was hard-deleted.
    Returns (deleted_count, orphaned_groups).
    """
    from procurement.models import GoodsReceipt, PurchaseReturn
    from sales.models import DeliveryNote, SalesPickup, SalesReturn
    from inventory.models import StockTransfer, StockAdjustment, DamagedReport, InventoryToSupplyTransfer
    from pos.models import POSSale, POSRefund
    from services.models import CustomerService

    model_map = {
        'GoodsReceipt': GoodsReceipt,
        'DeliveryNote': DeliveryNote,
        'SalesPickup': SalesPickup,
        'StockTransfer': StockTransfer,
        'StockAdjustment': StockAdjustment,
        'DamagedReport': DamagedReport,
        'POSSale': POSSale,
        'POSRefund': POSRefund,
        'InventoryToSupplyTransfer': InventoryToSupplyTransfer,
        'PurchaseReturn': PurchaseReturn,
        'SalesReturn': SalesReturn,
        'CustomerService': CustomerService,
    }

    total_deleted = 0
    orphaned_groups = 0

    # Also warn about completely unknown reference_types
    known_types = set(model_map.keys())
    unknown_type_moves = (
        StockMove.objects
        .filter(status=MoveStatus.POSTED)
        .exclude(reference_type__in=known_types)
        .exclude(reference_type='')
        .values_list('reference_type', flat=True)
        .distinct()
    )
    for utype in unknown_type_moves:
        warn_fn(f'    [ORPHAN] Unknown reference_type="{utype}" — cannot verify; skipping.')

    for ref_type, Model in model_map.items():
        # Collect all reference_ids used by POSTED moves of this type
        # (exclude NULL reference_id — those are special system/manual moves)
        move_ref_ids = set(
            StockMove.objects
            .filter(status=MoveStatus.POSTED, reference_type=ref_type)
            .exclude(reference_id__isnull=True)
            .values_list('reference_id', flat=True)
            .distinct()
        )
        if not move_ref_ids:
            continue

        # Find which of those IDs actually still exist in the source model
        # Use all_objects (via _all_manager) to include soft-deleted records —
        # a soft-deleted POSTED document is NOT orphaned; its moves are valid.
        mgr = _all_manager(Model)
        existing_ids = set(
            mgr.filter(pk__in=move_ref_ids).values_list('pk', flat=True)
        )
        orphaned_ids = move_ref_ids - existing_ids

        if not orphaned_ids:
            continue

        orphaned_qs = StockMove.objects.filter(
            status=MoveStatus.POSTED,
            reference_type=ref_type,
            reference_id__in=orphaned_ids,
        )

        for m in orphaned_qs.select_related('item').order_by('id')[:200]:  # log up to 200
            if ref_type == 'StockAdjustment':
                info_fn(
                    f'    [ADJ PRESERVED] Move#{m.pk} ref=StockAdjustment#{m.reference_id} '
                    f'item={m.item.code} qty={m.qty} '
                    f'(adjustment document deleted — move kept as intentional correction)'
                )
            else:
                info_fn(
                    f'    [ORPHAN] Move#{m.pk} ref={ref_type}#{m.reference_id} '
                    f'item={m.item.code} qty={m.qty} '
                    f'(source document deleted)'
                )

        count = orphaned_qs.count()
        if count > 200:
            info_fn(f'    [ORPHAN] ... and {count - 200} more orphaned moves for {ref_type}')

        # Manual/force adjustments represent intentional inventory corrections.
        # Preserve their moves even when the source StockAdjustment was hard-deleted.
        if ref_type == 'StockAdjustment':
            continue

        if not dry_run:
            orphaned_qs.delete()

        total_deleted += count
        orphaned_groups += len(orphaned_ids)

    return total_deleted, orphaned_groups


# ── Phase 1 helpers ──────────────────────────────────────────────────────────

def _fix_moves_for_doc(moves_qs, line_lookup_fn, warn_fn, dry_run, stats):
    """
    For each StockMove in moves_qs, call line_lookup_fn(move) to retrieve the
    source line.  Recalculate correct base-unit qty and update if changed.
    Conversion failures are recorded in _conversion_errors and the move is skipped.
    """
    for move in moves_qs.select_related('item__default_unit', 'item__selling_unit', 'unit'):
        line = line_lookup_fn(move)
        if line is None:
            stats['no_line'] += 1
            continue

        target_unit = _inventory_unit(move.item)

        line_qty = getattr(line, 'qty', None)
        line_unit = getattr(line, 'unit', None)
        if line_qty is None or line_unit is None:
            stats['no_line'] += 1
            continue

        # For adjustments the stored qty is abs(diff); we need to handle sign
        try:
            if move.move_type == 'ADJUST':
                raw_diff = line.qty_counted - line.qty_system
                if raw_diff == 0:
                    continue
                correct_qty = _safe_convert(
                    abs(raw_diff), line_unit, target_unit,
                    f"Move#{move.pk} ADJUST", warn_fn, item=move.item,
                )
            else:
                correct_qty = _safe_convert(
                    line_qty, line_unit, target_unit,
                    f"Move#{move.pk}", warn_fn, item=move.item,
                )
        except (ValueError, Exception):
            stats['conversion_error'] = stats.get('conversion_error', 0) + 1
            continue

        if correct_qty == move.qty and move.unit_id == target_unit.pk:
            stats['already_correct'] += 1
            continue

        if not dry_run:
            move.qty = correct_qty
            move.unit = target_unit
            move.save(update_fields=['qty', 'unit_id'])
        stats['updated'] += 1


def _document_reference_number(doc):
    return (
        getattr(doc, 'document_number', None)
        or getattr(doc, 'sale_no', None)
        or getattr(doc, 'refund_no', None)
        or getattr(doc, 'service_number', None)
        or ''
    )


def _document_posted_at(doc):
    return getattr(doc, 'posted_at', None) or getattr(doc, 'updated_at', None) or getattr(doc, 'created_at', None)


def _document_posted_by(doc):
    return getattr(doc, 'posted_by', None) or getattr(doc, 'created_by', None)


def _line_batch(line):
    return getattr(line, 'batch_number', '') or ''


def _line_serial(line):
    return getattr(line, 'serial_number', '') or ''


def _line_notes(ref_type, line):
    if ref_type == 'StockAdjustment':
        return f'Adjustment: system={line.qty_system}, counted={line.qty_counted}'
    if ref_type == 'DamagedReport':
        return getattr(line, 'reason', '') or ''
    if ref_type in ('PurchaseReturn', 'SalesReturn'):
        return getattr(line, 'reason', '') or ''
    return getattr(line, 'notes', '') or ''


def _line_move_type(ref_type):
    return {
        'GoodsReceipt': MoveType.RECEIVE,
        'DeliveryNote': MoveType.DELIVER,
        'SalesPickup': MoveType.DELIVER,
        'StockTransfer': MoveType.TRANSFER,
        'StockAdjustment': MoveType.ADJUST,
        'DamagedReport': MoveType.DAMAGE,
        'POSSale': MoveType.POS_SALE,
        'POSRefund': MoveType.RETURN_IN,
        'InventoryToSupplyTransfer': MoveType.SUPPLY_OUT,
        'PurchaseReturn': MoveType.RETURN_OUT,
        'SalesReturn': MoveType.RETURN_IN,
        'CustomerService': MoveType.SERVICE_OUT,
    }[ref_type]


def _service_default_location_id(doc):
    """Return the default pickable-location id for a CustomerService.

    Mirrors the real-time fallback used by ``services.views.service_complete``:
    when a ServiceLine has no location, the warehouse's lowest-coded pickable
    Location is used to post the StockMove.  The backfill and balance rebuild
    must apply the same fallback; otherwise they key off ``from_location=None``
    while the real move uses the concrete location, creating phantom duplicate
    moves on every resync run.
    """
    from warehouses.models import Location as _Location
    if not getattr(doc, 'warehouse_id', None):
        return None
    return (
        _Location.objects
        .filter(warehouse_id=doc.warehouse_id, is_pickable=True)
        .order_by('code')
        .values_list('id', flat=True)
        .first()
    )


def _line_locations(ref_type, doc, line, qty):
    if ref_type == 'GoodsReceipt':
        return None, line.location_id
    if ref_type == 'CustomerService':
        # ServiceLine.location is nullable — real-time posting falls back to the
        # warehouse's default pickable location. Keep parity here so backfilled
        # moves match the real move's from_location and don't get duplicated.
        loc_id = line.location_id or _service_default_location_id(doc)
        return loc_id, None
    if ref_type in ('DeliveryNote', 'SalesPickup', 'DamagedReport', 'PurchaseReturn', 'InventoryToSupplyTransfer'):
        return line.location_id, None
    if ref_type == 'StockTransfer':
        return line.from_location_id, line.to_location_id
    if ref_type == 'StockAdjustment':
        return (line.location_id, None) if qty < 0 else (None, line.location_id)
    if ref_type == 'POSSale':
        return (line.location_id or doc.location_id), None
    if ref_type == 'POSRefund':
        return None, line.location_id
    if ref_type == 'SalesReturn':
        return None, line.location_id
    return None, None


def _line_qty(ref_type, line, warn_fn):
    """Convert a document line's qty to the item's inventory unit.

    Returns None when the line should be skipped (zero diff for adjustments).
    Raises ValueError when no unit conversion exists — the caller must handle it.
    """
    item = line.item
    target_unit = _inventory_unit(item)
    if ref_type == 'StockAdjustment':
        raw_diff = line.qty_counted - line.qty_system
        if raw_diff == 0:
            return None
        qty = _safe_convert(abs(raw_diff), line.unit, target_unit, f'{ref_type} item={item.code}', warn_fn, item=item)
        return -qty if raw_diff < 0 else qty
    return _safe_convert(line.qty, line.unit, target_unit, f'{ref_type} item={item.code}', warn_fn, item=item)


def _ensure_grn_purchase_orders(warn_fn, dry_run, info_fn):
    from procurement.models import GoodsReceipt, PurchaseOrder, PurchaseOrderLine
    from inventory.services import generate_document_number

    created = 0
    grns = _all_manager(GoodsReceipt).filter(
        status=DocumentStatus.POSTED,
        purchase_order__isnull=True,
    ).prefetch_related('lines__item', 'lines__unit')

    for grn in grns:
        po = PurchaseOrder.objects.create(
            document_number=generate_document_number('PO', PurchaseOrder),
            supplier=grn.supplier,
            warehouse=grn.warehouse,
            order_date=grn.receipt_date,
            created_by=grn.created_by,
            status=DocumentStatus.APPROVED,
            approved_by=grn.posted_by or grn.created_by,
            approved_at=grn.posted_at or timezone.now(),
        )
        po_lines = []
        for line in grn.lines.all():
            po_lines.append(PurchaseOrderLine(
                purchase_order=po,
                item=line.item,
                qty_ordered=line.qty,
                qty_received=line.qty,
                unit=line.unit,
                unit_price=Decimal('0'),
                notes=line.notes,
            ))
        PurchaseOrderLine.objects.bulk_create(po_lines)
        grn.purchase_order = po
        grn.save(update_fields=['purchase_order', 'updated_at'])
        info_fn(f'  [PO BACKFILL] Created {po.document_number} for GRN {grn.document_number}')
        created += 1

    if dry_run:
        transaction.set_rollback(True)
    return created


def _iter_expected_moves(warn_fn):
    from procurement.models import GoodsReceipt, PurchaseReturn
    from sales.models import DeliveryNote, SalesPickup, SalesReturn
    from inventory.models import StockTransfer, StockAdjustment, DamagedReport, InventoryToSupplyTransfer
    from pos.models import POSSale, POSRefund, SaleStatus, RefundStatus
    from services.models import CustomerService, ServiceStatus

    doc_specs = [
        ('GoodsReceipt', _all_manager(GoodsReceipt).filter(status=DocumentStatus.POSTED).prefetch_related('lines__item__default_unit', 'lines__item__selling_unit', 'lines__unit', 'lines__location')),
        ('DeliveryNote', _all_manager(DeliveryNote).filter(status=DocumentStatus.POSTED).prefetch_related('lines__item__default_unit', 'lines__item__selling_unit', 'lines__unit', 'lines__location')),
        ('SalesPickup', _all_manager(SalesPickup).filter(status=DocumentStatus.POSTED).prefetch_related('lines__item__default_unit', 'lines__item__selling_unit', 'lines__unit', 'lines__location')),
        ('StockTransfer', _all_manager(StockTransfer).filter(status=DocumentStatus.POSTED).prefetch_related('lines__item__default_unit', 'lines__item__selling_unit', 'lines__unit', 'lines__from_location', 'lines__to_location')),
        ('StockAdjustment', _all_manager(StockAdjustment).filter(status=DocumentStatus.POSTED).prefetch_related('lines__item__default_unit', 'lines__item__selling_unit', 'lines__unit', 'lines__location')),
        ('DamagedReport', _all_manager(DamagedReport).filter(status=DocumentStatus.POSTED).prefetch_related('lines__item__default_unit', 'lines__item__selling_unit', 'lines__unit', 'lines__location')),
        ('POSSale', POSSale.objects.filter(status=SaleStatus.POSTED).prefetch_related('lines__item__default_unit', 'lines__item__selling_unit', 'lines__unit', 'lines__location').select_related('location')),
        ('POSRefund', POSRefund.objects.filter(status=RefundStatus.POSTED).prefetch_related('lines__item__default_unit', 'lines__item__selling_unit', 'lines__unit', 'lines__location')),
        ('InventoryToSupplyTransfer', _all_manager(InventoryToSupplyTransfer).filter(status=DocumentStatus.POSTED).prefetch_related('lines__item__default_unit', 'lines__item__selling_unit', 'lines__unit', 'lines__location')),
        ('PurchaseReturn', _all_manager(PurchaseReturn).filter(status=DocumentStatus.POSTED).prefetch_related('lines__item__default_unit', 'lines__item__selling_unit', 'lines__unit', 'lines__location')),
        ('SalesReturn', _all_manager(SalesReturn).filter(status=DocumentStatus.POSTED).prefetch_related('lines__item__default_unit', 'lines__item__selling_unit', 'lines__unit', 'lines__location')),
        ('CustomerService', CustomerService.objects.filter(status=ServiceStatus.COMPLETED).prefetch_related('lines__item__default_unit', 'lines__item__selling_unit', 'lines__unit', 'lines__location').select_related('warehouse')),
    ]

    for ref_type, docs in doc_specs:
        for doc in docs:
            for line in doc.lines.all():
                # Skip scrap service lines — they are NOT deducted from inventory
                if ref_type == 'CustomerService' and getattr(line, 'is_scrap', False):
                    continue
                try:
                    qty = _line_qty(ref_type, line, warn_fn)
                except (ValueError, Exception):
                    continue  # error already recorded in _conversion_errors
                if qty in (None, Decimal('0')):
                    continue
                from_location_id, to_location_id = _line_locations(ref_type, doc, line, qty)
                yield {
                    'reference_type': ref_type,
                    'reference_id': doc.pk,
                    'reference_number': _document_reference_number(doc),
                    'move_type': _line_move_type(ref_type),
                    'item': line.item,
                    'item_id': line.item_id,
                    'qty': abs(qty),
                    'unit': _inventory_unit(line.item),
                    'from_location_id': from_location_id,
                    'to_location_id': to_location_id,
                    'batch_number': _line_batch(line),
                    'serial_number': _line_serial(line),
                    'notes': _line_notes(ref_type, line),
                    'created_by': getattr(doc, 'created_by', None),
                    'posted_by': _document_posted_by(doc),
                    'posted_at': _document_posted_at(doc),
                }

    # ── Service bundle component moves (not represented by ServiceLine) ────────
    from services.models import CustomerService as _CustomerService, ServiceStatus as _ServiceStatus
    from warehouses.models import Location as _Location
    for svc in _CustomerService.objects.filter(
        status=_ServiceStatus.COMPLETED,
    ).prefetch_related(
        'bundles__price_list__items__item__default_unit',
        'bundles__price_list__items__item__selling_unit',
        'bundles__price_list__items__unit',
    ).select_related('warehouse'):
        if not svc.warehouse_id:
            continue
        default_loc_id = (
            _Location.objects
            .filter(warehouse_id=svc.warehouse_id, is_pickable=True)
            .order_by('code')
            .values_list('id', flat=True)
            .first()
        )
        if not default_loc_id:
            continue
        for bundle in svc.bundles.all():
            for pli in bundle.price_list.items.all():
                item = pli.item
                qty = (bundle.qty or Decimal('0')) * (pli.min_qty or Decimal('0'))
                if qty <= Decimal('0'):
                    continue
                target_unit = _inventory_unit(item)
                try:
                    base_qty = _safe_convert(
                        qty, pli.unit, target_unit,
                        f"CustomerService#{svc.pk} bundle={bundle.price_list.name} item={item.code}",
                        warn_fn, item=item,
                    )
                except (ValueError, Exception):
                    continue  # error already recorded in _conversion_errors
                if base_qty <= Decimal('0'):
                    continue
                yield {
                    'reference_type': 'CustomerService',
                    'reference_id': svc.pk,
                    'reference_number': _document_reference_number(svc),
                    'move_type': MoveType.SERVICE_OUT,
                    'item': item,
                    'item_id': item.pk,
                    'qty': base_qty,
                    'unit': target_unit,
                    'from_location_id': default_loc_id,
                    'to_location_id': None,
                    'batch_number': '',
                    'serial_number': '',
                    'notes': f'Bundle: {bundle.price_list.name}',
                    'created_by': getattr(svc, 'created_by', None),
                    'posted_by': _document_posted_by(svc),
                    'posted_at': _document_posted_at(svc),
                }

    # ── POS bundle component moves (not represented by POSSaleLine) ──────────
    for sale in POSSale.objects.filter(status=SaleStatus.POSTED).prefetch_related(
        'bundle_lines__price_list__items__item__default_unit',
        'bundle_lines__price_list__items__item__selling_unit',
        'bundle_lines__price_list__items__item__stock_unit',
        'bundle_lines__price_list__items__unit',
    ).select_related('location'):
        for bundle_line in sale.bundle_lines.all():
            for pli in bundle_line.price_list.items.all():
                item = pli.item
                qty = pli.min_qty * bundle_line.qty_sets
                if qty <= Decimal('0'):
                    continue
                target_unit = _inventory_unit(item)
                try:
                    base_qty = _safe_convert(
                        qty, pli.unit, target_unit,
                        f"POSSale#{sale.pk} bundle={bundle_line.price_list.name} item={item.code}",
                        warn_fn, item=item,
                    )
                except (ValueError, Exception):
                    continue  # error already recorded in _conversion_errors
                if base_qty <= Decimal('0'):
                    continue
                yield {
                    'reference_type': 'POSSale',
                    'reference_id': sale.pk,
                    'reference_number': sale.sale_no,
                    'move_type': MoveType.POS_SALE,
                    'item': item,
                    'item_id': item.pk,
                    'qty': base_qty,
                    'unit': target_unit,
                    'from_location_id': sale.location_id,
                    'to_location_id': None,
                    'batch_number': '',
                    'serial_number': '',
                    'notes': f'Bundle: {bundle_line.price_list.name}',
                    'created_by': getattr(sale, 'created_by', None),
                    'posted_by': _document_posted_by(sale),
                    'posted_at': _document_posted_at(sale),
                }


def _backfill_missing_moves(warn_fn, dry_run, info_fn):
    existing_keys = set(
        StockMove.objects.filter(status=MoveStatus.POSTED)
        .exclude(reference_number__startswith='REV-')
        .exclude(reference_number__startswith='VOID-')
        .values_list(
            'reference_type', 'reference_id', 'item_id', 'from_location_id', 'to_location_id', 'batch_number', 'serial_number'
        )
    )

    # Safety net against duplicate backfills: any move that already exists for
    # the same (ref_type, ref_id, item, batch, serial) with a CONCRETE
    # from/to location is treated as "already there."  Real-time posting is
    # the source of truth for the move's actual location (it applies warehouse
    # default-location fallbacks that the document lines don't record); the
    # backfill must never create a second move in a different location slot.
    # Phantom moves with NULL from/to location do NOT block backfill — those
    # are handled by Phase 0b cleanup after the real move is created.
    existing_loose_keys = set(
        StockMove.objects.filter(status=MoveStatus.POSTED)
        .exclude(reference_number__startswith='REV-')
        .exclude(reference_number__startswith='VOID-')
        .exclude(from_location_id__isnull=True, to_location_id__isnull=True)
        .values_list(
            'reference_type', 'reference_id', 'item_id', 'batch_number', 'serial_number'
        )
    )

    created = 0
    for payload in _iter_expected_moves(warn_fn):
        key = (
            payload['reference_type'],
            payload['reference_id'],
            payload['item_id'],
            payload['from_location_id'],
            payload['to_location_id'],
            payload['batch_number'],
            payload['serial_number'],
        )
        loose_key = (
            payload['reference_type'],
            payload['reference_id'],
            payload['item_id'],
            payload['batch_number'],
            payload['serial_number'],
        )
        if key in existing_keys or loose_key in existing_loose_keys:
            continue

        info_fn(
            f"    [BACKFILL] {payload['reference_type']}#{payload['reference_id']} item={payload['item'].code} qty={payload['qty']}"
        )
        if not dry_run:
            StockMove.objects.create(
                move_type=payload['move_type'],
                item=payload['item'],
                qty=payload['qty'],
                unit=payload['unit'],
                from_location_id=payload['from_location_id'],
                to_location_id=payload['to_location_id'],
                reference_type=payload['reference_type'],
                reference_id=payload['reference_id'],
                reference_number=payload['reference_number'],
                batch_number=payload['batch_number'],
                serial_number=payload['serial_number'],
                notes=payload['notes'],
                status=MoveStatus.POSTED,
                created_by=payload['created_by'],
                posted_by=payload['posted_by'],
                posted_at=payload['posted_at'],
            )
        existing_keys.add(key)
        existing_loose_keys.add(loose_key)
        created += 1

    return created


# ── Phase 1c helpers: recompute derived totals from posted documents ─────────

def _recompute_po_qty_received(dry_run, info_fn, warn_fn):
    """Reset every PO line's qty_received to 0, then replay all POSTED GRNs
    chronologically and increment qty_received in the PO LINE's OWN UNIT.

    Fixes data drift caused by the pre-fix bug where GRN unit ≠ PO unit
    inflated qty_received (GRN qty was added to a PO-unit field without
    converting).  Also fixes over-counting when a PO had multiple lines for
    the same item — we now pick a single best-matching PO line per GRN line.

    Returns (updated_lines, skipped_lines).
    """
    from procurement.models import GoodsReceipt, PurchaseOrderLine
    from inventory.services import _pick_po_line_for_grn

    # Reset on all PO lines that could have been touched by a posted GRN
    po_line_ids = set(
        GoodsReceipt.objects
        .filter(status=DocumentStatus.POSTED, purchase_order__isnull=False)
        .values_list('purchase_order__lines', flat=True)
    )
    po_line_ids.discard(None)

    if po_line_ids and not dry_run:
        PurchaseOrderLine.objects.filter(pk__in=po_line_ids).update(qty_received=Decimal('0'))
    info_fn(f'  [QTY-RECEIVED] Reset qty_received on {len(po_line_ids)} PO line(s).')

    grns = (
        _all_manager(GoodsReceipt)
        .filter(status=DocumentStatus.POSTED, purchase_order__isnull=False)
        .select_related('purchase_order')
        .prefetch_related(
            'lines__item', 'lines__unit',
            'purchase_order__lines__item', 'purchase_order__lines__unit',
        )
        .order_by('receipt_date', 'posted_at', 'pk')
    )

    # Running qty_received per PO line (so chronological order is honored
    # even when multiple GRNs hit the same PO).
    running = defaultdict(lambda: Decimal('0'))

    updated = 0
    skipped = 0
    for grn in grns:
        po = grn.purchase_order
        for line in grn.lines.all():
            po_line = _pick_po_line_for_grn(po, line.item, line.unit)
            if po_line is None:
                skipped += 1
                continue
            if po_line.unit_id == line.unit_id:
                received = line.qty or Decimal('0')
            else:
                try:
                    received = convert_to_base_unit(
                        line.qty, line.unit, po_line.unit, item=line.item,
                    )
                except (ValueError, Exception) as exc:
                    _conversion_errors.append(ConversionError(
                        item_code=line.item.code,
                        from_unit=getattr(line.unit, 'abbreviation', '?'),
                        to_unit=getattr(po_line.unit, 'abbreviation', '?'),
                        label=f'QTY-RECEIVED GRN {grn.document_number}',
                        message=str(exc),
                    ))
                    skipped += 1
                    continue
            running[po_line.pk] += received
            updated += 1

    if not dry_run and running:
        # Bulk apply running totals
        for pk, total in running.items():
            PurchaseOrderLine.objects.filter(pk=pk).update(qty_received=total)

    info_fn(f'  [QTY-RECEIVED] Applied {updated} GRN line(s); skipped {skipped}.')
    return updated, skipped


def _recompute_so_qty_delivered(dry_run, info_fn, warn_fn):
    """Reset SalesOrderLine.qty_delivered to 0, then replay all POSTED DNs
    and SalesPickups chronologically, incrementing qty_delivered in the
    SO line's OWN UNIT (converting where necessary).

    Soft-deleted (is_active=False) Sales Orders are excluded via
    sales_order__is_active=True on every query below: their qty_delivered is
    invisible to the app anyway, and processing them would (a) waste work
    recomputing tracking on a deleted order and (b) let a missing conversion
    on a deleted SO's line abort the whole resync. The reset set and the
    replay set MUST use the same filter so a line is never zeroed without
    being replayed (or vice versa). Actual stock-move rebuilding is unaffected
    — it runs off the DN/PU documents directly (via _all_manager), not the SO.
    """
    from sales.models import DeliveryNote, SalesPickup, SalesOrderLine
    from inventory.services import _pick_so_line

    so_line_ids = set(
        DeliveryNote.objects
        .filter(status=DocumentStatus.POSTED, sales_order__isnull=False,
                sales_order__is_active=True)
        .values_list('sales_order__lines', flat=True)
    )
    so_line_ids |= set(
        SalesPickup.objects
        .filter(status=DocumentStatus.POSTED, sales_order__isnull=False,
                sales_order__is_active=True)
        .values_list('sales_order__lines', flat=True)
    )
    so_line_ids.discard(None)

    if so_line_ids and not dry_run:
        SalesOrderLine.objects.filter(pk__in=so_line_ids).update(qty_delivered=Decimal('0'))
    info_fn(f'  [QTY-DELIVERED] Reset qty_delivered on {len(so_line_ids)} SO line(s).')

    fulfilment_docs = []
    for dn in (DeliveryNote.objects
               .filter(status=DocumentStatus.POSTED, sales_order__isnull=False,
                       sales_order__is_active=True)
               .select_related('sales_order')
               .prefetch_related(
                   'lines__item', 'lines__unit',
                   'sales_order__lines__item', 'sales_order__lines__unit',
               )):
        fulfilment_docs.append((_document_posted_at(dn) or timezone.now(), 'DN', dn))
    for pu in (SalesPickup.objects
               .filter(status=DocumentStatus.POSTED, sales_order__isnull=False,
                       sales_order__is_active=True)
               .select_related('sales_order')
               .prefetch_related(
                   'lines__item', 'lines__unit',
                   'sales_order__lines__item', 'sales_order__lines__unit',
               )):
        fulfilment_docs.append((_document_posted_at(pu) or timezone.now(), 'PU', pu))
    fulfilment_docs.sort(key=lambda t: (t[0], t[1], t[2].pk))

    running = defaultdict(lambda: Decimal('0'))
    updated = 0
    skipped = 0
    for _ts, _kind, doc in fulfilment_docs:
        so = doc.sales_order
        for line in doc.lines.all():
            so_line = _pick_so_line(so, line.item, line.unit)
            if so_line is None:
                skipped += 1
                continue
            if so_line.unit_id == line.unit_id:
                delivered = line.qty or Decimal('0')
            else:
                try:
                    delivered = convert_to_base_unit(
                        line.qty, line.unit, so_line.unit, item=line.item,
                    )
                except (ValueError, Exception) as exc:
                    _conversion_errors.append(ConversionError(
                        item_code=line.item.code,
                        from_unit=getattr(line.unit, 'abbreviation', '?'),
                        to_unit=getattr(so_line.unit, 'abbreviation', '?'),
                        label=f'QTY-DELIVERED {doc.document_number}',
                        message=str(exc),
                    ))
                    skipped += 1
                    continue
            running[so_line.pk] += delivered
            updated += 1

    if not dry_run and running:
        for pk, total in running.items():
            SalesOrderLine.objects.filter(pk=pk).update(qty_delivered=total)

    info_fn(f'  [QTY-DELIVERED] Applied {updated} fulfilment line(s); skipped {skipped}.')
    return updated, skipped


def _recompute_item_cost_price(dry_run, info_fn, warn_fn):
    """Rebuild Item.cost_price via chronological weighted-average-cost replay.

    For every POSTED GoodsReceipt (in receipt_date, posted_at, pk order):
      - For each line: convert qty to stock_unit, convert PO unit_price to
        price per stock_unit (factor-based, NOT conversion_price), distribute
        delivery_charge proportionally by line value (denominated in stock_unit
        so mixed GRN/PO units don't corrupt the proportion).
      - Apply weighted-average:
          new_cost = (old_qty * old_cost + base_qty * landed_per_stock) / new_qty

    Items with no priceable receipts (all GRN lines had unit_price=0 on the PO)
    are SKIPPED at write-back so their existing cost_price is preserved.
    This prevents the resync from zeroing out manually-assigned cost prices
    for items whose purchase orders were saved without a unit price.
    """
    from procurement.models import GoodsReceipt
    from catalog.models import Item
    from catalog.utils import convert_price_for_unit

    state = {}           # item_id -> (running_qty_in_stock_unit, cost_per_stock_unit)
    has_priced_receipt = set()  # item_ids that had at least one non-zero landed cost

    grns = (
        _all_manager(GoodsReceipt)
        .filter(status=DocumentStatus.POSTED)
        .select_related('purchase_order')
        .prefetch_related(
            'lines__item__default_unit', 'lines__unit',
            'purchase_order__lines__item', 'purchase_order__lines__unit',
        )
        .order_by('receipt_date', 'posted_at', 'pk')
    )

    grn_count = 0
    line_count = 0
    skipped_lines = 0

    for grn in grns:
        grn_count += 1
        po = grn.purchase_order
        delivery_charge = grn.delivery_charge or Decimal('0')

        # ── First pass: resolve PO prices and convert value to stock_unit so
        # the delivery-charge proportion is in a consistent unit even when the
        # GRN unit differs from the PO unit (e.g. GRN in bx, PO in pcs).
        per_line = []
        total_value_in_stock = Decimal('0')
        for line in grn.lines.all():
            po_unit_price = Decimal('0')
            po_unit = None
            if po is not None:
                po_line = (
                    po.lines.filter(item=line.item, unit=line.unit).first()
                    or po.lines.filter(item=line.item).first()
                )
                if po_line is not None:
                    po_unit_price = po_line.unit_price or Decimal('0')
                    po_unit = po_line.unit

            stock_unit = line.item.default_unit

            # Convert po_unit_price → price per stock_unit for value calculation.
            # This keeps all "value" terms in the same unit so proportions are correct.
            po_price_per_stock_for_value = po_unit_price
            if po_unit_price > 0 and po_unit is not None and getattr(po_unit, 'pk', None) != stock_unit.pk:
                try:
                    po_price_per_stock_for_value = convert_price_for_unit(
                        po_unit_price, po_unit, stock_unit,
                        item=line.item, use_conversion_price=False,
                        raise_on_missing=True,
                    )
                except (ValueError, Exception):
                    po_price_per_stock_for_value = Decimal('0')  # no conversion → exclude from delivery proportion

            # Convert line qty to stock_unit for value computation
            try:
                base_qty_for_value = _safe_convert(
                    line.qty, line.unit, stock_unit,
                    f'GRN#{grn.pk} value-pass item={line.item.code}',
                    warn_fn, item=line.item,
                )
            except (ValueError, Exception):
                base_qty_for_value = Decimal('0')

            value_in_stock = (base_qty_for_value or Decimal('0')) * po_price_per_stock_for_value
            per_line.append({
                'line': line,
                'po_unit_price': po_unit_price,
                'po_unit': po_unit,
                'value_in_stock': value_in_stock,
            })
            total_value_in_stock += value_in_stock

        n_lines = len(per_line)
        for rec in per_line:
            line = rec['line']
            item = line.item
            stock_unit = item.default_unit
            po_unit_price = rec['po_unit_price']
            po_unit = rec['po_unit'] or line.unit

            try:
                base_qty = _safe_convert(
                    line.qty, line.unit, stock_unit,
                    f'GRN#{grn.pk} cost-replay item={item.code}',
                    warn_fn, item=item,
                )
            except (ValueError, Exception):
                skipped_lines += 1
                continue
            if base_qty is None or base_qty <= 0:
                continue

            if po_unit_price > 0 and getattr(po_unit, 'pk', None) != stock_unit.pk:
                try:
                    po_price_per_stock = convert_price_for_unit(
                        po_unit_price, po_unit, stock_unit,
                        item=item, use_conversion_price=False,
                        raise_on_missing=True,
                    )
                except (ValueError, Exception) as exc:
                    _conversion_errors.append(ConversionError(
                        item_code=item.code,
                        from_unit=getattr(po_unit, 'abbreviation', '?'),
                        to_unit=getattr(stock_unit, 'abbreviation', '?'),
                        label=f'COST GRN {grn.document_number}',
                        message=str(exc),
                    ))
                    skipped_lines += 1
                    continue
            else:
                po_price_per_stock = po_unit_price

            # Distribute delivery charge proportionally by value (in stock_unit).
            line_delivery_share = Decimal('0')
            if delivery_charge > 0 and total_value_in_stock > 0:
                line_delivery_share = delivery_charge * (rec['value_in_stock'] / total_value_in_stock)
            elif delivery_charge > 0 and n_lines > 0:
                line_delivery_share = delivery_charge / n_lines
            delivery_per_stock = (line_delivery_share / base_qty) if base_qty else Decimal('0')

            landed_per_stock = po_price_per_stock + delivery_per_stock

            old_qty, old_cost = state.get(item.pk, (Decimal('0'), Decimal('0')))
            new_qty = old_qty + base_qty
            if landed_per_stock > 0 and new_qty > 0:
                new_cost = (old_qty * old_cost + base_qty * landed_per_stock) / new_qty
                state[item.pk] = (new_qty, new_cost)
                has_priced_receipt.add(item.pk)
            else:
                # Free receipt (no PO price) — qty grows, cost unchanged.
                state[item.pk] = (new_qty, old_cost)
            line_count += 1

    updated = 0
    unchanged = 0
    preserved = 0
    for item_id, (_qty, cost) in state.items():
        try:
            item = Item.objects.only('pk', 'code', 'cost_price').get(pk=item_id)
        except Item.DoesNotExist:
            continue
        new_cost = (cost or Decimal('0')).quantize(Decimal('0.0001'))
        old_cost = (item.cost_price or Decimal('0')).quantize(Decimal('0.0001'))

        # If every GRN for this item had unit_price=0 (no priced receipt), do NOT
        # overwrite an existing cost_price with 0.  The resync would otherwise
        # zero out manually-assigned or previously-computed costs every time it
        # runs for items whose PO lines were saved without a price.
        if new_cost == Decimal('0') and item_id not in has_priced_receipt:
            if old_cost > Decimal('0'):
                info_fn(
                    f'    [COST] {item.code}: preserved {old_cost} '
                    f'(all GRN receipts had zero PO price — fill in PO unit_price to update)'
                )
                preserved += 1
            else:
                unchanged += 1
            continue

        if new_cost == old_cost:
            unchanged += 1
            continue
        if not dry_run:
            Item.objects.filter(pk=item_id).update(cost_price=new_cost)
        info_fn(f'    [COST] {item.code}: {old_cost} → {new_cost}')
        updated += 1

    info_fn(
        f'  [COST] Walked {grn_count} GRN(s), {line_count} priceable line(s); '
        f'updated {updated} item cost(s), preserved {preserved} (no PO price), '
        f'unchanged {unchanged}, skipped {skipped_lines}.'
    )
    return updated, unchanged, skipped_lines, preserved


# ── line-lookup functions per document type ──────────────────────────────────

def _make_grn_lookup():
    from procurement.models import GoodsReceiptLine
    cache = {}
    def lookup(move):
        key = (
            move.reference_id,
            move.item_id,
            move.to_location_id,
            move.batch_number or '',
            move.serial_number or '',
            move.unit_id,
        )
        if key not in cache:
            qs = GoodsReceiptLine.objects.filter(
                goods_receipt_id=move.reference_id,
                item_id=move.item_id,
                location_id=move.to_location_id,
            )
            if move.batch_number:
                qs = qs.filter(batch_number=move.batch_number)
            if move.serial_number:
                qs = qs.filter(serial_number=move.serial_number)

            line = qs.select_related('unit').filter(unit_id=move.unit_id).first()
            if line is None:
                line = qs.select_related('unit').first()
            if line is None:
                line = GoodsReceiptLine.objects.filter(
                    goods_receipt_id=move.reference_id,
                    item_id=move.item_id,
                ).select_related('unit').first()
            cache[key] = line
        return cache[key]
    return lookup


def _make_dn_lookup():
    from sales.models import DeliveryLine
    cache = {}
    def lookup(move):
        key = (move.reference_id, move.item_id)
        if key not in cache:
            cache[key] = DeliveryLine.objects.filter(
                delivery_id=move.reference_id, item_id=move.item_id
            ).select_related('unit').first()
        return cache[key]
    return lookup


def _make_pickup_lookup():
    from sales.models import SalesPickupLine
    cache = {}
    def lookup(move):
        key = (move.reference_id, move.item_id)
        if key not in cache:
            cache[key] = SalesPickupLine.objects.filter(
                pickup_id=move.reference_id, item_id=move.item_id
            ).select_related('unit').first()
        return cache[key]
    return lookup


def _make_transfer_lookup():
    from inventory.models import StockTransferLine
    cache = {}
    def lookup(move):
        key = (move.reference_id, move.item_id)
        if key not in cache:
            cache[key] = StockTransferLine.objects.filter(
                transfer_id=move.reference_id, item_id=move.item_id
            ).select_related('unit').first()
        return cache[key]
    return lookup


def _make_adjustment_lookup():
    from inventory.models import StockAdjustmentLine
    cache = {}
    def lookup(move):
        key = (move.reference_id, move.item_id)
        if key not in cache:
            cache[key] = StockAdjustmentLine.objects.filter(
                adjustment_id=move.reference_id, item_id=move.item_id
            ).select_related('unit').first()
        return cache[key]
    return lookup


def _make_damaged_lookup():
    from inventory.models import DamagedReportLine
    cache = {}
    def lookup(move):
        key = (move.reference_id, move.item_id)
        if key not in cache:
            cache[key] = DamagedReportLine.objects.filter(
                report_id=move.reference_id, item_id=move.item_id
            ).select_related('unit').first()
        return cache[key]
    return lookup


def _make_pos_sale_lookup():
    from pos.models import POSSaleLine
    cache = {}
    def lookup(move):
        key = (move.reference_id, move.item_id)
        if key not in cache:
            cache[key] = POSSaleLine.objects.filter(
                sale_id=move.reference_id, item_id=move.item_id
            ).select_related('unit').first()
        return cache[key]
    return lookup


def _make_pos_refund_lookup():
    from pos.models import POSRefundLine
    cache = {}
    def lookup(move):
        key = (move.reference_id, move.item_id)
        if key not in cache:
            cache[key] = POSRefundLine.objects.filter(
                refund_id=move.reference_id, item_id=move.item_id
            ).select_related('unit').first()
        return cache[key]
    return lookup


def _make_ist_lookup():
    from inventory.models import InventoryToSupplyTransferLine
    cache = {}
    def lookup(move):
        key = (move.reference_id, move.item_id)
        if key not in cache:
            cache[key] = InventoryToSupplyTransferLine.objects.filter(
                transfer_id=move.reference_id, item_id=move.item_id
            ).select_related('unit').first()
        return cache[key]
    return lookup


def _make_purchase_return_lookup():
    from procurement.models import PurchaseReturnLine
    cache = {}
    def lookup(move):
        key = (move.reference_id, move.item_id)
        if key not in cache:
            cache[key] = PurchaseReturnLine.objects.filter(
                purchase_return_id=move.reference_id, item_id=move.item_id
            ).select_related('unit').first()
        return cache[key]
    return lookup


def _make_sales_return_lookup():
    from sales.models import SalesReturnLine
    cache = {}
    def lookup(move):
        key = (move.reference_id, move.item_id)
        if key not in cache:
            cache[key] = SalesReturnLine.objects.filter(
                sales_return_id=move.reference_id, item_id=move.item_id
            ).select_related('unit').first()
        return cache[key]
    return lookup


def _make_service_lookup():
    from services.models import ServiceLine, ServiceBundle
    from collections import namedtuple
    _FakeLine = namedtuple('_FakeLine', ['qty', 'unit'])
    cache = {}
    def lookup(move):
        key = (move.reference_id, move.item_id)
        if key not in cache:
            # Try non-scrap product line first
            sl = ServiceLine.objects.filter(
                service_id=move.reference_id,
                item_id=move.item_id,
                is_scrap=False,
            ).select_related('unit').first()
            if sl is not None:
                cache[key] = sl
            else:
                # Fall back to bundle items — aggregate qty across all bundles
                total_qty = Decimal('0')
                bundle_unit = None
                for bndl in ServiceBundle.objects.filter(
                    service_id=move.reference_id,
                ).select_related('price_list').prefetch_related(
                    'price_list__items__item', 'price_list__items__unit'
                ):
                    for pli in bndl.price_list.items.filter(item_id=move.item_id):
                        total_qty += (bndl.qty or Decimal('0')) * (pli.min_qty or Decimal('0'))
                        bundle_unit = pli.unit
                if total_qty > Decimal('0') and bundle_unit is not None:
                    cache[key] = _FakeLine(qty=total_qty, unit=bundle_unit)
                else:
                    cache[key] = None
        return cache[key]
    return lookup


REFERENCE_TYPE_LOOKUPS = {
    'GoodsReceipt': _make_grn_lookup,
    'DeliveryNote': _make_dn_lookup,
    'SalesPickup': _make_pickup_lookup,
    'StockTransfer': _make_transfer_lookup,
    'StockAdjustment': _make_adjustment_lookup,
    'DamagedReport': _make_damaged_lookup,
    'POSSale': _make_pos_sale_lookup,
    'POSRefund': _make_pos_refund_lookup,
    'InventoryToSupplyTransfer': _make_ist_lookup,
    'PurchaseReturn': _make_purchase_return_lookup,
    'SalesReturn': _make_sales_return_lookup,
    'CustomerService': _make_service_lookup,
}


# ── Phase 2 helpers ──────────────────────────────────────────────────────────

def _accumulate(bucket, item_id, location_id, delta):
    # Skip entries with no valid location or item – they cannot become a StockBalance row
    if item_id is None or location_id is None:
        return
    bucket[(item_id, location_id)] += delta


def _build_balance_from_documents(warn_fn):
    """
    Walk every POSTED document in CHRONOLOGICAL ORDER (by posted_at/created_at),
    apply correct base-unit conversion, accumulate (item, location) → qty_on_hand delta.
    Returns a defaultdict.
    
    This replays inventory history as it actually happened, processing all document
    types (GRN, DN, Adjustments, etc.) in the order they were posted/created.
    """
    from procurement.models import GoodsReceipt, PurchaseReturn
    from sales.models import DeliveryNote, SalesPickup, SalesReturn
    from inventory.models import StockTransfer, StockAdjustment, DamagedReport, InventoryToSupplyTransfer
    from pos.models import POSSale, POSRefund, SaleStatus, RefundStatus
    from services.models import CustomerService, ServiceStatus
    from warehouses.models import Location as _WLocation

    bal = defaultdict(Decimal)

    # ══════════════════════════════════════════════════════════════════════════
    # COLLECT ALL DOCUMENTS WITH THEIR POSTED/CREATED DATES
    # ══════════════════════════════════════════════════════════════════════════
    
    all_documents = []
    
    # Helper to get document date (prefer posted_at, fallback to created_at)
    def _doc_date(doc):
        return getattr(doc, 'posted_at', None) or getattr(doc, 'created_at', None) or timezone.now()
    
    # ── GoodsReceipt ────────────────────────────────────────────────────────
    for grn in _all_manager(GoodsReceipt).filter(status=DocumentStatus.POSTED).prefetch_related(
        'lines__item__default_unit', 'lines__item__selling_unit', 'lines__unit', 'lines__location'
    ):
        all_documents.append(('GoodsReceipt', grn, _doc_date(grn)))

    # ── DeliveryNote ────────────────────────────────────────────────────────
    for dn in _all_manager(DeliveryNote).filter(status=DocumentStatus.POSTED).prefetch_related(
        'lines__item__default_unit', 'lines__item__selling_unit', 'lines__unit', 'lines__location'
    ):
        all_documents.append(('DeliveryNote', dn, _doc_date(dn)))

    # ── SalesPickup ─────────────────────────────────────────────────────────
    for sp in _all_manager(SalesPickup).filter(status=DocumentStatus.POSTED).prefetch_related(
        'lines__item__default_unit', 'lines__item__selling_unit', 'lines__unit', 'lines__location'
    ):
        all_documents.append(('SalesPickup', sp, _doc_date(sp)))

    # ── StockTransfer ────────────────────────────────────────────────────────
    for tr in _all_manager(StockTransfer).filter(status=DocumentStatus.POSTED).prefetch_related(
        'lines__item__default_unit', 'lines__item__selling_unit', 'lines__unit',
        'lines__from_location', 'lines__to_location'
    ):
        all_documents.append(('StockTransfer', tr, _doc_date(tr)))

    # ── StockAdjustment ──────────────────────────────────────────────────────
    for adj in _all_manager(StockAdjustment).filter(status=DocumentStatus.POSTED).prefetch_related(
        'lines__item__default_unit', 'lines__item__selling_unit', 'lines__unit', 'lines__location'
    ):
        all_documents.append(('StockAdjustment', adj, _doc_date(adj)))

    # ── DamagedReport ────────────────────────────────────────────────────────
    for dr in _all_manager(DamagedReport).filter(status=DocumentStatus.POSTED).prefetch_related(
        'lines__item__default_unit', 'lines__item__selling_unit', 'lines__unit', 'lines__location'
    ):
        all_documents.append(('DamagedReport', dr, _doc_date(dr)))

    # ── POSSale ──────────────────────────────────────────────────────────────
    for sale in POSSale.objects.filter(status=SaleStatus.POSTED).prefetch_related(
        'lines__item__default_unit', 'lines__item__selling_unit', 'lines__unit', 'lines__location',
        'bundle_lines__price_list__items__item__default_unit',
        'bundle_lines__price_list__items__item__selling_unit',
        'bundle_lines__price_list__items__item__stock_unit',
        'bundle_lines__price_list__items__unit',
    ).select_related('location'):
        all_documents.append(('POSSale', sale, _doc_date(sale)))

    # ── POSRefund ────────────────────────────────────────────────────────────
    for refund in POSRefund.objects.filter(status=RefundStatus.POSTED).prefetch_related(
        'lines__item__default_unit', 'lines__item__selling_unit', 'lines__unit', 'lines__location'
    ):
        all_documents.append(('POSRefund', refund, _doc_date(refund)))

    # ── InventoryToSupplyTransfer ────────────────────────────────────────────
    for ist in _all_manager(InventoryToSupplyTransfer).filter(status=DocumentStatus.POSTED).prefetch_related(
        'lines__item__default_unit', 'lines__item__selling_unit', 'lines__unit', 'lines__location'
    ):
        all_documents.append(('InventoryToSupplyTransfer', ist, _doc_date(ist)))

    # ── PurchaseReturn ───────────────────────────────────────────────────────
    for pr in _all_manager(PurchaseReturn).filter(status=DocumentStatus.POSTED).prefetch_related(
        'lines__item__default_unit', 'lines__item__selling_unit', 'lines__unit', 'lines__location'
    ):
        all_documents.append(('PurchaseReturn', pr, _doc_date(pr)))

    # ── SalesReturn ──────────────────────────────────────────────────────────
    for sr in _all_manager(SalesReturn).filter(status=DocumentStatus.POSTED).prefetch_related(
        'lines__item__default_unit', 'lines__item__selling_unit', 'lines__unit', 'lines__location'
    ):
        all_documents.append(('SalesReturn', sr, _doc_date(sr)))

    # ── CustomerService ──────────────────────────────────────────────────────
    for svc in CustomerService.objects.filter(status=ServiceStatus.COMPLETED).prefetch_related(
        'lines__item__default_unit', 'lines__item__selling_unit', 'lines__unit', 'lines__location',
        'bundles__price_list__items__item__default_unit',
        'bundles__price_list__items__item__selling_unit',
        'bundles__price_list__items__unit',
    ).select_related('warehouse'):
        all_documents.append(('CustomerService', svc, _doc_date(svc)))

    # ══════════════════════════════════════════════════════════════════════════
    # SORT ALL DOCUMENTS BY DATE (CHRONOLOGICAL ORDER)
    # ══════════════════════════════════════════════════════════════════════════
    
    all_documents.sort(key=lambda x: (x[2], x[0], x[1].pk))  # Sort by date, then type, then ID
    
    warn_fn(f"  [CHRONOLOGICAL] Processing {len(all_documents)} documents in chronological order...")
    
    # Track document type counts for reporting
    doc_type_counts = defaultdict(int)
    
    # ══════════════════════════════════════════════════════════════════════════
    # PROCESS DOCUMENTS IN CHRONOLOGICAL ORDER
    # ══════════════════════════════════════════════════════════════════════════
    
    for doc_type, doc, doc_date in all_documents:
        doc_type_counts[doc_type] += 1
        
        if doc_type == 'GoodsReceipt':
            for line in doc.lines.all():
                target_unit = _inventory_unit(line.item)
                try:
                    q = _safe_convert(line.qty, line.unit, target_unit,
                                      f"GRN#{doc.pk} item={line.item.code}", warn_fn, item=line.item)
                except (ValueError, Exception):
                    continue
                _accumulate(bal, line.item_id, line.location_id, q)
        
        elif doc_type == 'DeliveryNote':
            for line in doc.lines.all():
                target_unit = _inventory_unit(line.item)
                try:
                    q = _safe_convert(line.qty, line.unit, target_unit,
                                      f"DN#{doc.pk} item={line.item.code}", warn_fn, item=line.item)
                except (ValueError, Exception):
                    continue
                _accumulate(bal, line.item_id, line.location_id, -q)
        
        elif doc_type == 'SalesPickup':
            for line in doc.lines.all():
                target_unit = _inventory_unit(line.item)
                try:
                    q = _safe_convert(line.qty, line.unit, target_unit,
                                      f"Pickup#{doc.pk} item={line.item.code}", warn_fn, item=line.item)
                except (ValueError, Exception):
                    continue
                _accumulate(bal, line.item_id, line.location_id, -q)
        
        elif doc_type == 'StockTransfer':
            for line in doc.lines.all():
                target_unit = _inventory_unit(line.item)
                try:
                    q = _safe_convert(line.qty, line.unit, target_unit,
                                      f"Transfer#{doc.pk} item={line.item.code}", warn_fn, item=line.item)
                except (ValueError, Exception):
                    continue
                _accumulate(bal, line.item_id, line.from_location_id, -q)
                _accumulate(bal, line.item_id, line.to_location_id, q)
        
        elif doc_type == 'StockAdjustment':
            # SET-to-counted semantics: post_adjustment writes
            #   balance.qty_on_hand = qty_counted
            # discarding the prior balance. A diff-based replay
            # (accumulate qty_counted - qty_system) only matches when
            # qty_system equalled the running balance at the time of post —
            # if any prior document was edited, the historical qty_system
            # is stale and the diff replay drifts.
            # Setting the (item, location) bucket directly to the converted
            # qty_counted preserves the SET intent across replays.
            for line in doc.lines.all():
                if line.location_id is None:
                    continue
                target_unit = _inventory_unit(line.item)
                try:
                    new_qty = _safe_convert(
                        line.qty_counted, line.unit, target_unit,
                        f"Adj#{doc.pk} item={line.item.code}", warn_fn,
                        item=line.item,
                    )
                except (ValueError, Exception):
                    continue
                bal[(line.item_id, line.location_id)] = new_qty
        
        elif doc_type == 'DamagedReport':
            for line in doc.lines.all():
                target_unit = _inventory_unit(line.item)
                try:
                    q = _safe_convert(line.qty, line.unit, target_unit,
                                      f"Damaged#{doc.pk} item={line.item.code}", warn_fn, item=line.item)
                except (ValueError, Exception):
                    continue
                _accumulate(bal, line.item_id, line.location_id, -q)
        
        elif doc_type == 'POSSale':
            for line in doc.lines.all():
                loc_id = line.location_id or doc.location_id
                target_unit = _inventory_unit(line.item)
                try:
                    q = _safe_convert(line.qty, line.unit, target_unit,
                                      f"POSSale#{doc.pk} item={line.item.code}", warn_fn, item=line.item)
                except (ValueError, Exception):
                    continue
                _accumulate(bal, line.item_id, loc_id, -q)
            
            # Bundle component deductions
            for bundle_line in doc.bundle_lines.all():
                for pli in bundle_line.price_list.items.all():
                    item = pli.item
                    qty = pli.min_qty * bundle_line.qty_sets
                    if qty <= Decimal('0'):
                        continue
                    target_unit = _inventory_unit(item)
                    try:
                        q = _safe_convert(qty, pli.unit, target_unit,
                                          f"POSSale#{doc.pk} bundle={bundle_line.price_list.name} item={item.code}",
                                          warn_fn, item=item)
                    except (ValueError, Exception):
                        continue
                    _accumulate(bal, item.pk, doc.location_id, -q)
        
        elif doc_type == 'POSRefund':
            for line in doc.lines.all():
                target_unit = _inventory_unit(line.item)
                try:
                    q = _safe_convert(line.qty, line.unit, target_unit,
                                      f"POSRefund#{doc.pk} item={line.item.code}", warn_fn, item=line.item)
                except (ValueError, Exception):
                    continue
                _accumulate(bal, line.item_id, line.location_id, q)
        
        elif doc_type == 'InventoryToSupplyTransfer':
            for line in doc.lines.all():
                target_unit = _inventory_unit(line.item)
                try:
                    q = _safe_convert(line.qty, line.unit, target_unit,
                                      f"IST#{doc.pk} item={line.item.code}", warn_fn, item=line.item)
                except (ValueError, Exception):
                    continue
                _accumulate(bal, line.item_id, line.location_id, -q)
        
        elif doc_type == 'PurchaseReturn':
            for line in doc.lines.all():
                target_unit = _inventory_unit(line.item)
                try:
                    q = _safe_convert(line.qty, line.unit, target_unit,
                                      f"PurchReturn#{doc.pk} item={line.item.code}", warn_fn, item=line.item)
                except (ValueError, Exception):
                    continue
                _accumulate(bal, line.item_id, line.location_id, -q)
        
        elif doc_type == 'SalesReturn':
            for line in doc.lines.all():
                target_unit = _inventory_unit(line.item)
                try:
                    q = _safe_convert(line.qty, line.unit, target_unit,
                                      f"SalesReturn#{doc.pk} item={line.item.code}", warn_fn, item=line.item)
                except (ValueError, Exception):
                    continue
                _accumulate(bal, line.item_id, line.location_id, q)
        
        elif doc_type == 'CustomerService':
            # Product lines (skip scrap)
            svc_default_loc = None
            for line in doc.lines.all():
                if getattr(line, 'is_scrap', False):
                    continue
                # Match real-time posting's NULL-location fallback
                # (services.views.service_complete uses the warehouse's default
                # pickable location when line.location is not set).
                loc_id = line.location_id
                if loc_id is None:
                    if svc_default_loc is None:
                        svc_default_loc = _service_default_location_id(doc)
                    loc_id = svc_default_loc
                if loc_id is None:
                    # Truly unresolvable: no warehouse or no pickable location.
                    continue
                target_unit = _inventory_unit(line.item)
                try:
                    q = _safe_convert(line.qty, line.unit, target_unit,
                                      f"Service#{doc.pk} item={line.item.code}", warn_fn, item=line.item)
                except (ValueError, Exception):
                    continue
                _accumulate(bal, line.item_id, loc_id, -q)
            
            # Bundle component deductions
            if doc.warehouse_id:
                default_loc_id = (
                    _WLocation.objects
                    .filter(warehouse_id=doc.warehouse_id, is_pickable=True)
                    .order_by('code')
                    .values_list('id', flat=True)
                    .first()
                )
                if default_loc_id:
                    for bundle in doc.bundles.all():
                        for pli in bundle.price_list.items.all():
                            item = pli.item
                            bundle_qty = (bundle.qty or Decimal('0')) * (pli.min_qty or Decimal('0'))
                            if bundle_qty <= Decimal('0'):
                                continue
                            target_unit = _inventory_unit(item)
                            try:
                                q = _safe_convert(
                                    bundle_qty, pli.unit, target_unit,
                                    f"Service#{doc.pk} bundle item={item.code}", warn_fn, item=item,
                                )
                            except (ValueError, Exception):
                                continue
                            _accumulate(bal, item.pk, default_loc_id, -q)
    
    # Report document type counts
    warn_fn("  [CHRONOLOGICAL] Document counts by type:")
    for doc_type in sorted(doc_type_counts.keys()):
        warn_fn(f"    {doc_type:<30} {doc_type_counts[doc_type]:>5} documents")

    return bal


# ── Command ──────────────────────────────────────────────────────────────────

class Command(BaseCommand):
    help = (
        'Re-sync StockBalance and StockMove records from scratch. '
        'Phase 0: delete orphaned moves + deduplicate. '
        'Phase 1: fix move qtys and backfill missing moves. '
        'Phase 2: rebuild StockBalance from all posted documents. '
        'Applies changes by default; use --dry-run to preview without saving.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            default=False,
            help='Preview changes without writing to the database.',
        )
        parser.add_argument(
            '--phase',
            choices=['0', '1', '2', '3', '4', '5', 'all'],
            default='all',
            help='0=clean moves, 1=fix qtys, 2=recalc balances, 3=audit, 4=financials, 5=log, all=all.',
        )
        parser.add_argument(
            '--quiet', '-q',
            action='store_true',
            default=False,
            help='Suppress per-document output; only show summary.',
        )
        parser.add_argument(
            '--detect-only',
            action='store_true',
            default=False,
            help=(
                'Scan for Phase 0 auto-fix candidates (orphans, duplicates, excess) '
                'and emit a JSON catalog to stdout. No changes are written.'
            ),
        )
        parser.add_argument(
            '--apply-fixes',
            default=None,
            help=(
                'Path to a JSON file listing approved Phase 0 fix IDs. '
                'Only the listed move IDs are deleted; then phases 1-5 run as usual.'
            ),
        )

    # ── internal output helpers ──────────────────────────────────────────────

    @staticmethod
    def _safe_str(msg):
        """Return msg with non-ASCII chars replaced so cp1252 consoles don't crash."""
        return msg.encode('ascii', errors='replace').decode('ascii')

    def _info(self, msg):
        if not self._quiet:
            try:
                self.stdout.write(msg)
            except UnicodeEncodeError:
                self.stdout.write(self._safe_str(msg))

    def _warn(self, msg):
        try:
            self.stdout.write(self.style.WARNING(msg))
        except UnicodeEncodeError:
            self.stdout.write(self.style.WARNING(self._safe_str(msg)))

    # ── entry point ──────────────────────────────────────────────────────────

    def handle(self, *args, **options):
        self._quiet = options['quiet']
        dry_run = options['dry_run']
        phase = options['phase']
        detect_only = options.get('detect_only', False)
        apply_fixes_path = options.get('apply_fixes')

        # Reset the global error collector at the start of each run.
        _conversion_errors.clear()

        # ── Detect-only short path ────────────────────────────────────────
        if detect_only:
            self._emit_detect_json()
            return

        # ── Load approved selection (if any) ──────────────────────────────
        self._approved_selection = None
        if apply_fixes_path:
            import json as _json
            try:
                with open(apply_fixes_path, 'r', encoding='utf-8') as f:
                    raw = _json.load(f)
                self._approved_selection = {
                    'orphan_move_ids': set(int(x) for x in raw.get('orphan_move_ids') or []),
                    'duplicate_move_ids': set(int(x) for x in raw.get('duplicate_move_ids') or []),
                    'excess_move_ids': set(int(x) for x in raw.get('excess_move_ids') or []),
                }
                # Loose duplicates use the same deletion path as strict duplicates.
                self._approved_selection['duplicate_move_ids'] |= set(
                    int(x) for x in raw.get('loose_duplicate_move_ids') or []
                )
            except Exception as exc:
                self.stdout.write(self.style.ERROR(
                    f'Could not read --apply-fixes file {apply_fixes_path}: {exc}'
                ))
                return

        # Track what was changed for the audit log
        self._resync_summary = {
            'started_at': timezone.now().isoformat(),
            'dry_run': dry_run,
            'phase': phase,
            'changes': {},
        }

        mode = 'DRY-RUN' if dry_run else 'APPLYING'
        self.stdout.write(self.style.SUCCESS(
            f'\n=== resync_inventory [{mode}] phase={phase} ===\n'
        ))

        if dry_run:
            self.stdout.write(self.style.WARNING(
                '  No changes will be saved.  Re-run without --dry-run to commit.\n'
            ))

        # Phases 0-2 mutate StockMove/StockBalance based on unit conversions.
        # They run inside one shared transaction so that a missing conversion
        # discovered anywhere among them aborts the WHOLE mutating run —
        # never partially apply moves/balances derived from a silently
        # skipped (unconverted) line.
        #
        # IMPORTANT: this app's DB router can send writes to 'default' (Neon)
        # or to 'local_cache' (SQLite mirror) depending on SYNC_MODE — a bare
        # transaction.atomic() only ever covers 'default' and would silently
        # let 'local_cache' writes commit even when we mean to abort. Wrap
        # every alias that's actually configured (desktop-mode settings only
        # define 'default') so the abort/rollback below is real regardless
        # of which connection the router picked.
        write_aliases = [a for a in ('default', 'local_cache') if a in connections.databases]

        # This block holds one long transaction on 'local_cache' spanning
        # thousands of rows. The background sync worker (started for the
        # live runserver process — see sync/apps.py) runs on its own thread
        # and would otherwise fight this transaction for SQLite's single
        # writer lock on every batch, stalling the request for minutes or
        # raising "database is locked". Pause it for the duration and always
        # resume it afterward, even on abort.
        from sync.background_sync import pause_worker, resume_worker
        pause_worker()
        try:
            with ExitStack() as mutation_txn:
                for alias in write_aliases:
                    mutation_txn.enter_context(transaction.atomic(using=alias))

                if phase in ('0', 'all'):
                    self._run_phase0(dry_run)
                if phase in ('1', 'all'):
                    self._run_phase1(dry_run)
                if phase in ('2', 'all'):
                    self._run_phase2(dry_run)

                if _conversion_errors:
                    self._report_conversion_errors()
                    if not dry_run:
                        for alias in write_aliases:
                            transaction.set_rollback(True, using=alias)
                        raise CommandError(
                            f'Aborted: {len(_conversion_errors)} unit conversion(s) missing '
                            '(see [SKIP] lines above). No changes were saved — add the '
                            'missing UnitConversion record(s), then re-run resync_inventory.'
                        )

                if dry_run:
                    # Some sub-steps (e.g. GRN->PO backfill) write unconditionally
                    # and rely on this outer rollback for dry-run safety — make
                    # sure that actually covers whichever alias got written to.
                    for alias in write_aliases:
                        transaction.set_rollback(True, using=alias)
        finally:
            resume_worker()

        if phase in ('3', 'all'):
            self._run_phase3()

        if phase in ('4', 'all'):
            self._run_phase4(dry_run)

        if phase in ('5', 'all') and not dry_run:
            self._run_phase5()

        self.stdout.write(self.style.SUCCESS('\n=== Done ===\n'))

    # ── Phase 4: Recalculate financial statements ────────────────────────────

    def _run_phase4(self, dry_run):
        """Recalculate MonthlyCashflowSummary for all months with data."""
        self.stdout.write('\n--- Phase 4: Recalculating financial statements ---')

        try:
            from cashflow.monthly_signals import update_monthly_summary
            from cashflow.models import MonthlyCashflowSummary

            # Find all months that have summaries
            periods = list(
                MonthlyCashflowSummary.objects
                .values_list('year', 'month')
                .distinct()
                .order_by('year', 'month')
            )

            if not periods:
                self.stdout.write('  No monthly summaries to recalculate.')
                return

            recalculated = 0
            for year, month in periods:
                if not dry_run:
                    update_monthly_summary(year, month)
                recalculated += 1

            mode = '(dry-run) would recalculate' if dry_run else 'Recalculated'
            self.stdout.write(self.style.SUCCESS(
                f'  {mode} {recalculated} monthly financial statement(s).'
            ))
            self._resync_summary['changes']['financial_months_recalculated'] = recalculated

        except ImportError:
            self.stdout.write(self.style.WARNING(
                '  Skipped — cashflow.monthly_signals not available.'
            ))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'  Error recalculating financials: {e}'))

    # ── Phase 5: Create audit log entry ──────────────────────────────────────

    def _run_phase5(self):
        """Record what the resync changed in the ManualLog table."""
        self.stdout.write('\n--- Phase 5: Creating audit log ---')

        try:
            from audit.models import ManualLog

            summary = self._resync_summary
            summary['completed_at'] = timezone.now().isoformat()
            changes = summary.get('changes', {})

            # Build a human-readable description
            parts = []
            if changes.get('orphaned_deleted'):
                parts.append(f"{changes['orphaned_deleted']} orphaned moves deleted")
            if changes.get('duplicates_removed'):
                parts.append(f"{changes['duplicates_removed']} duplicate moves removed")
            if changes.get('excess_deleted'):
                parts.append(f"{changes['excess_deleted']} excess moves deleted")
            if changes.get('moves_corrected'):
                parts.append(f"{changes['moves_corrected']} move quantities corrected")
            if changes.get('moves_backfilled'):
                parts.append(f"{changes['moves_backfilled']} missing moves backfilled")
            if changes.get('po_qty_received_lines'):
                parts.append(f"{changes['po_qty_received_lines']} PO line(s) qty_received recomputed")
            if changes.get('so_qty_delivered_lines'):
                parts.append(f"{changes['so_qty_delivered_lines']} SO line(s) qty_delivered recomputed")
            if changes.get('item_cost_updated'):
                parts.append(f"{changes['item_cost_updated']} item cost_price recomputed via WAC")
            if changes.get('item_cost_preserved'):
                parts.append(f"{changes['item_cost_preserved']} item cost_price preserved (unpriced PO lines)")
            if changes.get('balances_updated'):
                parts.append(f"{changes['balances_updated']} balances updated")
            if changes.get('balances_created'):
                parts.append(f"{changes['balances_created']} balances created")
            if changes.get('financial_months_recalculated'):
                parts.append(f"{changes['financial_months_recalculated']} financial months recalculated")
            if changes.get('negative_balances'):
                parts.append(f"{changes['negative_balances']} negative balance(s) detected")
            if changes.get('invoices_no_cogs'):
                parts.append(f"{changes['invoices_no_cogs']} invoice(s) missing COGS")
            if changes.get('items_no_selling_unit'):
                parts.append(f"{changes['items_no_selling_unit']} item(s) missing selling unit")

            if not parts:
                parts.append('No changes needed — data was already consistent')

            reason = 'resync_inventory: ' + '; '.join(parts)

            ManualLog.objects.create(
                user=None,  # system action
                action='FIX',
                table_name='inventory_stockbalance, inventory_stockmove',
                record_id='',
                fields_changed='qty_on_hand, qty, status',
                old_value='',
                new_value=str(changes),
                reason=reason,
                notes=f'Phase: {summary["phase"]}, Started: {summary["started_at"]}',
            )
            self.stdout.write(self.style.SUCCESS(f'  Logged: {reason}'))

        except ImportError:
            self.stdout.write(self.style.WARNING('  Skipped — audit.models not available.'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'  Error creating audit log: {e}'))

    def _report_conversion_errors(self):
        """Print a de-duplicated summary of lines skipped due to missing conversions."""
        seen = set()
        unique_errors = []
        for err in _conversion_errors:
            if err.key not in seen:
                seen.add(err.key)
                unique_errors.append(err)

        # Always print — --quiet must not hide the reason a real run aborted.
        self._warn(f'  [SKIP] {len(unique_errors)} item(s) have lines skipped — no unit conversion configured:')
        for err in sorted(unique_errors, key=lambda e: e.item_code):
            self._warn(f'    {err.item_code:40s}  {err.from_unit} → {err.to_unit}')

    # ── Phase 0: clean up StockMoves ─────────────────────────────────────────

    def _run_phase0(self, dry_run):
        # If a selection was supplied via --apply-fixes, delete only those IDs.
        if self._approved_selection is not None:
            self._run_phase0_selective(dry_run)
            return

        # Step 0a: remove orphaned moves (document deleted, move not cleaned up)
        self.stdout.write('\n--- Phase 0a: Removing orphaned StockMoves ---')
        deleted, orph_groups = _delete_orphaned_moves(dry_run, self._warn, self._info)
        mode = '(dry-run) would delete' if dry_run else 'Deleted'
        self.stdout.write(self.style.SUCCESS(
            f'  {mode} {deleted} orphaned move(s) across {orph_groups} missing document(s).'
        ))
        if dry_run and deleted:
            self.stdout.write(self.style.WARNING(
                '  Re-run without --dry-run to commit deletions.'
            ))

        # Step 0b: remove exact duplicate moves
        self.stdout.write('\n--- Phase 0b: Deduplicating StockMoves ---')
        removed, groups = _deduplicate_moves(dry_run, self._warn)
        mode = '(dry-run) would remove' if dry_run else 'Removed'
        self.stdout.write(self.style.SUCCESS(
            f'  {mode} {removed} duplicate move(s) across {groups} group(s).'
        ))
        if dry_run and removed:
            self.stdout.write(self.style.WARNING(
                '  Re-run without --dry-run to commit removals.'
            ))

        # Step 0c: remove excess moves whose document line was deleted in admin
        self.stdout.write('\n--- Phase 0c: Removing excess moves (deleted lines) ---')
        excess = self._delete_excess_moves(dry_run)
        mode = '(dry-run) would delete' if dry_run else 'Deleted'
        self.stdout.write(self.style.SUCCESS(
            f'  {mode} {excess} excess move(s) for deleted document lines.'
        ))

        self._resync_summary['changes']['orphaned_deleted'] = deleted
        self._resync_summary['changes']['duplicates_removed'] = removed
        self._resync_summary['changes']['excess_deleted'] = excess

    # ── Phase 0 (selective): delete only approved move IDs ───────────────────

    def _run_phase0_selective(self, dry_run):
        """Phase 0 variant that deletes only the move IDs the user approved
        via --apply-fixes. Unchecked candidates are preserved."""
        sel = self._approved_selection or {}
        orphan_ids = sel.get('orphan_move_ids') or set()
        dupe_ids = sel.get('duplicate_move_ids') or set()
        excess_ids = sel.get('excess_move_ids') or set()

        self.stdout.write('\n--- Phase 0a: Removing orphaned StockMoves (selective) ---')
        deleted_orph = self._delete_moves_by_ids(orphan_ids, dry_run, 'ORPHAN')
        mode = '(dry-run) would delete' if dry_run else 'Deleted'
        self.stdout.write(self.style.SUCCESS(
            f'  {mode} {deleted_orph} orphaned move(s) (user-approved).'
        ))

        self.stdout.write('\n--- Phase 0b: Deduplicating StockMoves (selective) ---')
        deleted_dupe = self._delete_moves_by_ids(dupe_ids, dry_run, 'DEDUP')
        self.stdout.write(self.style.SUCCESS(
            f'  {mode} {deleted_dupe} duplicate move(s) (user-approved).'
        ))

        self.stdout.write('\n--- Phase 0c: Removing excess moves (selective) ---')
        deleted_excess = self._delete_moves_by_ids(excess_ids, dry_run, 'EXCESS')
        self.stdout.write(self.style.SUCCESS(
            f'  {mode} {deleted_excess} excess move(s) (user-approved).'
        ))

        self._resync_summary['changes']['orphaned_deleted'] = deleted_orph
        self._resync_summary['changes']['duplicates_removed'] = deleted_dupe
        self._resync_summary['changes']['excess_deleted'] = deleted_excess

    def _delete_moves_by_ids(self, move_ids, dry_run, tag):
        """Delete StockMoves with ids in ``move_ids`` (iterable of int).

        Returns the number of moves deleted (or that would be deleted).
        """
        if not move_ids:
            return 0
        qs = StockMove.objects.filter(pk__in=move_ids).select_related('item')
        count = 0
        for m in qs:
            self._info(
                f'    [{tag}] Move#{m.pk} ref={m.reference_type}#{m.reference_id} '
                f'item={m.item.code} qty={m.qty}'
            )
            if not dry_run:
                m.delete()
            count += 1
        return count

    # ── Detection (called with --detect-only) ────────────────────────────────

    def _emit_detect_json(self):
        """Scan for Phase 0 auto-fix candidates and print a JSON catalog.

        Output is wrapped between BEGIN_DETECT_JSON / END_DETECT_JSON markers so
        the caller can extract it reliably from stdout.
        """
        import json as _json

        catalog = {
            'orphans': self._detect_orphan_moves(),
            'duplicates': self._detect_duplicate_moves(),
            'loose_duplicates': self._detect_loose_duplicate_moves(),
            'excess': self._detect_excess_moves(),
        }
        catalog['totals'] = {
            'orphans': len(catalog['orphans']),
            'duplicates': sum(len(g['moves']) - 1 for g in catalog['duplicates']),
            'duplicate_groups': len(catalog['duplicates']),
            'loose_duplicates': sum(len(g['moves']) - 1 for g in catalog['loose_duplicates']),
            'loose_duplicate_groups': len(catalog['loose_duplicates']),
            'excess': len(catalog['excess']),
        }

        # Emit markers so the view can find the payload regardless of other noise
        self.stdout.write('BEGIN_DETECT_JSON')
        self.stdout.write(_json.dumps(catalog, default=str))
        self.stdout.write('END_DETECT_JSON')

    def _detect_orphan_moves(self):
        """Return a list of orphan-move records (document no longer exists).

        StockAdjustment moves are intentionally excluded — manual/force adjustments
        are always preserved even when their source document was deleted.
        """
        from procurement.models import GoodsReceipt, PurchaseReturn
        from sales.models import DeliveryNote, SalesPickup, SalesReturn
        from inventory.models import (
            StockTransfer, DamagedReport, InventoryToSupplyTransfer,
        )
        from pos.models import POSSale, POSRefund
        from services.models import CustomerService

        model_map = {
            'GoodsReceipt': GoodsReceipt,
            'DeliveryNote': DeliveryNote,
            'SalesPickup': SalesPickup,
            'StockTransfer': StockTransfer,
            # StockAdjustment excluded — manual adjustments are always preserved
            'DamagedReport': DamagedReport,
            'POSSale': POSSale,
            'POSRefund': POSRefund,
            'InventoryToSupplyTransfer': InventoryToSupplyTransfer,
            'PurchaseReturn': PurchaseReturn,
            'SalesReturn': SalesReturn,
            'CustomerService': CustomerService,
        }

        records = []
        for ref_type, Model in model_map.items():
            move_ref_ids = set(
                StockMove.objects
                .filter(status=MoveStatus.POSTED, reference_type=ref_type)
                .exclude(reference_id__isnull=True)
                .values_list('reference_id', flat=True)
                .distinct()
            )
            if not move_ref_ids:
                continue
            mgr = _all_manager(Model)
            existing_ids = set(
                mgr.filter(pk__in=move_ref_ids).values_list('pk', flat=True)
            )
            orphaned_ids = move_ref_ids - existing_ids
            if not orphaned_ids:
                continue
            moves = (
                StockMove.objects
                .filter(status=MoveStatus.POSTED, reference_type=ref_type,
                        reference_id__in=orphaned_ids)
                .select_related('item', 'unit')
                .order_by('id')
            )
            for m in moves:
                records.append({
                    'move_id': m.pk,
                    'reference_type': ref_type,
                    'reference_id': m.reference_id,
                    'reference_number': m.reference_number,
                    'item_code': m.item.code,
                    'item_name': m.item.name,
                    'qty': str(m.qty),
                    'unit': getattr(m.unit, 'abbreviation', ''),
                    'posted_at': m.posted_at.isoformat() if m.posted_at else None,
                })
        return records

    def _detect_duplicate_moves(self):
        """Return duplicate-move groups.

        A group is keyed by (reference_type, reference_id, item_id,
        from_location_id, to_location_id, batch_number, serial_number).
        Each group lists every move in the group; the "keep" hint is the
        lowest pk (same rule Phase 0b uses when deleting).
        """
        from django.db.models import Count

        dup_keys = list(
            StockMove.objects
            .filter(status=MoveStatus.POSTED)
            .exclude(reference_number__startswith='REV-')
            .exclude(reference_number__startswith='VOID-')
            .values('reference_type', 'reference_id', 'item_id',
                    'from_location_id', 'to_location_id',
                    'batch_number', 'serial_number')
            .annotate(cnt=Count('id'))
            .filter(cnt__gt=1)
        )

        groups = []
        for key in dup_keys:
            moves = list(
                StockMove.objects.filter(
                    reference_type=key['reference_type'],
                    reference_id=key['reference_id'],
                    item_id=key['item_id'],
                    from_location_id=key['from_location_id'],
                    to_location_id=key['to_location_id'],
                    batch_number=key['batch_number'],
                    serial_number=key['serial_number'],
                    status=MoveStatus.POSTED,
                )
                .exclude(reference_number__startswith='REV-')
                .exclude(reference_number__startswith='VOID-')
                .order_by('id')
                .select_related('item', 'unit', 'from_location', 'to_location')
            )
            if len(moves) < 2:
                continue
            keep = moves[0].pk
            group_payload = {
                'reference_type': key['reference_type'],
                'reference_id': key['reference_id'],
                'reference_number': moves[0].reference_number,
                'item_code': moves[0].item.code,
                'item_name': moves[0].item.name,
                'keep_move_id': keep,
                'moves': [],
            }
            for m in moves:
                group_payload['moves'].append({
                    'move_id': m.pk,
                    'qty': str(m.qty),
                    'unit': getattr(m.unit, 'abbreviation', ''),
                    'from_location': str(m.from_location) if m.from_location_id else None,
                    'to_location': str(m.to_location) if m.to_location_id else None,
                    'batch': m.batch_number or '',
                    'serial': m.serial_number or '',
                    'posted_at': m.posted_at.isoformat() if m.posted_at else None,
                    'is_keep': m.pk == keep,
                })
            groups.append(group_payload)
        return groups

    def _detect_loose_duplicate_moves(self):
        """Return "loose" duplicate groups keyed only by (ref_type, ref_id, item_id).

        These are moves that share the same source document + item but differ in
        from_location / to_location / batch / serial. Phase 0b does NOT delete
        these automatically because each NULL vs concrete location is treated as
        distinct. They are surfaced for operator review (pattern: service lines
        with NULL location producing a duplicate move alongside a real one on
        the warehouse default location).
        """
        from django.db.models import Count

        loose_keys = list(
            StockMove.objects
            .filter(status=MoveStatus.POSTED)
            .exclude(reference_number__startswith='REV-')
            .exclude(reference_number__startswith='VOID-')
            .values('reference_type', 'reference_id', 'item_id')
            .annotate(cnt=Count('id'))
            .filter(cnt__gt=1)
        )

        # Subtract strict duplicates so the same move isn't listed twice
        strict_move_ids = set()
        for g in self._detect_duplicate_moves():
            for m in g['moves']:
                strict_move_ids.add(m['move_id'])

        groups = []
        for key in loose_keys:
            moves = list(
                StockMove.objects.filter(
                    reference_type=key['reference_type'],
                    reference_id=key['reference_id'],
                    item_id=key['item_id'],
                    status=MoveStatus.POSTED,
                )
                .exclude(reference_number__startswith='REV-')
                .exclude(reference_number__startswith='VOID-')
                .order_by('id')
                .select_related('item', 'unit', 'from_location', 'to_location')
            )
            if len(moves) < 2:
                continue
            if all(m.pk in strict_move_ids for m in moves):
                continue

            # Prefer keeping the move with a concrete from/to location; drop the
            # NULL-location phantom so real inventory impact is preserved.
            def _has_loc(m):
                return m.from_location_id is not None or m.to_location_id is not None
            with_loc = [m for m in moves if _has_loc(m)]
            keep_id = (with_loc or moves)[0].pk

            group_payload = {
                'reference_type': key['reference_type'],
                'reference_id': key['reference_id'],
                'reference_number': moves[0].reference_number,
                'item_code': moves[0].item.code,
                'item_name': moves[0].item.name,
                'keep_move_id': keep_id,
                'moves': [],
            }
            for m in moves:
                group_payload['moves'].append({
                    'move_id': m.pk,
                    'qty': str(m.qty),
                    'unit': getattr(m.unit, 'abbreviation', ''),
                    'from_location': str(m.from_location) if m.from_location_id else None,
                    'to_location': str(m.to_location) if m.to_location_id else None,
                    'batch': m.batch_number or '',
                    'serial': m.serial_number or '',
                    'posted_at': m.posted_at.isoformat() if m.posted_at else None,
                    'is_keep': m.pk == keep_id,
                })
            groups.append(group_payload)
        return groups

    def _detect_excess_moves(self):
        """Return moves whose source document EXISTS but the matching line is gone.

        StockAdjustment moves are intentionally excluded — manual/force adjustments
        are always preserved even when their source line was deleted.

        A cross-check verifies the source document still exists before flagging
        a move as excess — moves whose document is also gone are orphans (handled
        by Phase 0a) and must not appear as excess candidates.
        """
        from procurement.models import GoodsReceipt, PurchaseReturn
        from sales.models import DeliveryNote, SalesPickup, SalesReturn
        from inventory.models import StockTransfer, DamagedReport, InventoryToSupplyTransfer
        from pos.models import POSSale, POSRefund
        from services.models import CustomerService

        doc_model_map = {
            'GoodsReceipt': GoodsReceipt,
            'DeliveryNote': DeliveryNote,
            'SalesPickup': SalesPickup,
            'StockTransfer': StockTransfer,
            'DamagedReport': DamagedReport,
            'POSSale': POSSale,
            'POSRefund': POSRefund,
            'InventoryToSupplyTransfer': InventoryToSupplyTransfer,
            'PurchaseReturn': PurchaseReturn,
            'SalesReturn': SalesReturn,
            'CustomerService': CustomerService,
        }

        records = []
        for ref_type, lookup_factory in REFERENCE_TYPE_LOOKUPS.items():
            if ref_type == 'StockAdjustment':
                continue  # Manual adjustments are always preserved
            Model = doc_model_map.get(ref_type)
            moves = (
                StockMove.objects
                .filter(reference_type=ref_type, status=MoveStatus.POSTED)
                .exclude(reference_id__isnull=True)
                .exclude(reference_number__startswith='REV-')
                .exclude(reference_number__startswith='VOID-')
                .select_related('item', 'unit')
            )
            lookup_fn = lookup_factory()
            for move in moves:
                line = lookup_fn(move)
                if line is None:
                    # Cross-check: only flag as excess if the source document
                    # actually exists. If it's gone too, it's an orphan (Phase 0a),
                    # not an excess — skip to avoid a false positive.
                    if Model is not None:
                        mgr = _all_manager(Model)
                        if not mgr.filter(pk=move.reference_id).exists():
                            continue
                    records.append({
                        'move_id': move.pk,
                        'reference_type': ref_type,
                        'reference_id': move.reference_id,
                        'reference_number': move.reference_number,
                        'item_code': move.item.code,
                        'item_name': move.item.name,
                        'qty': str(move.qty),
                        'unit': getattr(move.unit, 'abbreviation', ''),
                        'posted_at': move.posted_at.isoformat() if move.posted_at else None,
                    })
        return records

    def _delete_excess_moves(self, dry_run):
        """
        Delete POSTED StockMoves whose source document still EXISTS but the
        specific line item was deleted in admin.  The move references a
        (document, item) pair that no longer has a matching line.

        StockAdjustment moves are never deleted — manual corrections are preserved.

        A cross-check verifies the source document exists before deleting.
        If the document is also gone the move is an orphan (Phase 0a's job),
        not an excess, and is skipped to avoid an incorrect deletion.
        Moves with no reference_id are also skipped for the same reason.
        """
        from procurement.models import GoodsReceipt, PurchaseReturn
        from sales.models import DeliveryNote, SalesPickup, SalesReturn
        from inventory.models import StockTransfer, StockAdjustment, DamagedReport, InventoryToSupplyTransfer
        from pos.models import POSSale, POSRefund
        from services.models import CustomerService

        doc_model_map = {
            'GoodsReceipt': GoodsReceipt,
            'DeliveryNote': DeliveryNote,
            'SalesPickup': SalesPickup,
            'StockTransfer': StockTransfer,
            'StockAdjustment': StockAdjustment,
            'DamagedReport': DamagedReport,
            'POSSale': POSSale,
            'POSRefund': POSRefund,
            'InventoryToSupplyTransfer': InventoryToSupplyTransfer,
            'PurchaseReturn': PurchaseReturn,
            'SalesReturn': SalesReturn,
            'CustomerService': CustomerService,
        }

        deleted = 0
        for ref_type, lookup_factory in REFERENCE_TYPE_LOOKUPS.items():
            Model = doc_model_map.get(ref_type)
            moves = (
                StockMove.objects.filter(
                    reference_type=ref_type, status=MoveStatus.POSTED,
                )
                .exclude(reference_id__isnull=True)
                .exclude(reference_number__startswith='REV-')
                .exclude(reference_number__startswith='VOID-')
                .select_related('item')
            )
            lookup_fn = lookup_factory()
            for move in moves:
                line = lookup_fn(move)
                if line is None:
                    if ref_type == 'StockAdjustment':
                        # Manual/force adjustments are intentional corrections — keep
                        # the move even when the StockAdjustmentLine was later deleted.
                        self._info(
                            f'    [ADJ PRESERVED] Move#{move.pk} StockAdjustment#{move.reference_id} '
                            f'item={move.item.code} qty={move.qty} — line missing but move kept'
                        )
                        continue

                    # Cross-check: confirm the source document still exists.
                    # If it's gone too, this is an orphan (Phase 0a handles it),
                    # not a true excess — skip to prevent an incorrect deletion.
                    if Model is not None:
                        mgr = _all_manager(Model)
                        if not mgr.filter(pk=move.reference_id).exists():
                            self._warn(
                                f'    [SKIP-ORPHAN] Move#{move.pk} {ref_type}#{move.reference_id} '
                                f'item={move.item.code} — source document not found; '
                                f'skipping excess deletion (Phase 0a will clean this)'
                            )
                            continue

                    # Source document exists but the specific line is gone — true excess.
                    self._info(
                        f'    [EXCESS] Move#{move.pk} {ref_type}#{move.reference_id} '
                        f'item={move.item.code} qty={move.qty} — line deleted'
                    )
                    if not dry_run:
                        move.delete()
                    deleted += 1
        return deleted

    # ── Phase 1: fix StockMove.qty ───────────────────────────────────────────

    def _run_phase1(self, dry_run):
        self.stdout.write('\n--- Phase 1: Correcting StockMove quantities ---')

        total_stats = {'updated': 0, 'already_correct': 0, 'no_line': 0, 'backfilled': 0, 'conversion_error': 0}

        with transaction.atomic():
            po_backfilled = _ensure_grn_purchase_orders(self._warn, dry_run, self._info)
            if dry_run:
                transaction.set_rollback(True)
        self._info(f'  Missing GRN purchase orders created: {po_backfilled}')

        for ref_type, lookup_factory in REFERENCE_TYPE_LOOKUPS.items():
            moves_qs = StockMove.objects.filter(
                reference_type=ref_type,
                status=MoveStatus.POSTED,
            ).exclude(reference_number__startswith='REV-')

            count = moves_qs.count()
            if count == 0:
                continue

            self._info(f'  {ref_type:<35} {count:>5} moves')
            stats = {'updated': 0, 'already_correct': 0, 'no_line': 0, 'conversion_error': 0}
            lookup_fn = lookup_factory()

            with transaction.atomic():
                _fix_moves_for_doc(moves_qs, lookup_fn, self._warn, dry_run, stats)
                if dry_run:
                    transaction.set_rollback(True)

            self._info(
                f'    -> updated={stats["updated"]}  '
                f'ok={stats["already_correct"]}  '
                f'missing_line={stats["no_line"]}'
            )
            for k, v in stats.items():
                total_stats[k] += v

        with transaction.atomic():
            backfilled = _backfill_missing_moves(self._warn, dry_run, self._info)
            if dry_run:
                transaction.set_rollback(True)
        self._info(f'  Missing moves backfilled: {backfilled}')
        total_stats['backfilled'] += backfilled

        # ── Phase 1c: rebuild derived totals from posted documents ──────
        # Fixes drift from the pre-fix bug where line.qty (in the document's
        # own unit) was added to PO/SO unit fields without converting, and
        # where Item.cost_price was averaged using mixed units.
        self.stdout.write('\n--- Phase 1c: Recomputing derived totals ---')

        with transaction.atomic():
            qr_updated, qr_skipped = _recompute_po_qty_received(dry_run, self._info, self._warn)
            if dry_run:
                transaction.set_rollback(True)
        self._resync_summary['changes']['po_qty_received_lines'] = qr_updated
        self._resync_summary['changes']['po_qty_received_skipped'] = qr_skipped

        with transaction.atomic():
            qd_updated, qd_skipped = _recompute_so_qty_delivered(dry_run, self._info, self._warn)
            if dry_run:
                transaction.set_rollback(True)
        self._resync_summary['changes']['so_qty_delivered_lines'] = qd_updated
        self._resync_summary['changes']['so_qty_delivered_skipped'] = qd_skipped

        with transaction.atomic():
            cost_updated, cost_unchanged, cost_skipped, cost_preserved = _recompute_item_cost_price(
                dry_run, self._info, self._warn,
            )
            if dry_run:
                transaction.set_rollback(True)
        self._resync_summary['changes']['item_cost_updated'] = cost_updated
        self._resync_summary['changes']['item_cost_unchanged'] = cost_unchanged
        self._resync_summary['changes']['item_cost_skipped'] = cost_skipped
        self._resync_summary['changes']['item_cost_preserved'] = cost_preserved

        # Fix reversal moves: their qty should mirror the corrected original
        rev_moves = StockMove.objects.filter(
            reference_number__startswith='REV-',
            status=MoveStatus.POSTED,
        ).select_related('item__default_unit', 'item__selling_unit', 'unit')

        rev_updated = 0
        for rev in rev_moves:
            # Find the original move this reversal was created from
            orig_ref = rev.reference_number[4:]  # strip 'REV-'
            orig = StockMove.objects.select_related('item__default_unit', 'item__selling_unit', 'unit').filter(
                reference_type=rev.reference_type,
                reference_id=rev.reference_id,
                reference_number=orig_ref,
                status=MoveStatus.POSTED,
            ).first()
            if orig and (orig.qty != rev.qty or orig.unit_id != rev.unit_id):
                if not dry_run:
                    rev.qty = orig.qty
                    rev.unit = orig.unit
                    rev.save(update_fields=['qty', 'unit_id'])
                rev_updated += 1

        self._info(f'  Reversal moves corrected: {rev_updated}')
        total_stats['updated'] += rev_updated

        self.stdout.write(self.style.SUCCESS(
            f'\n  Phase 1 total — updated: {total_stats["updated"]}  '
            f'already_correct: {total_stats["already_correct"]}  '
            f'missing_source: {total_stats["no_line"]}  '
            f'backfilled: {total_stats["backfilled"]}'
        ))

        self._resync_summary['changes']['moves_corrected'] = total_stats['updated']
        self._resync_summary['changes']['moves_backfilled'] = total_stats['backfilled']

    # ── Phase 2: recalculate StockBalance from document lines ────────────────

    def _run_phase2(self, dry_run):
        self.stdout.write('\n--- Phase 2: Recalculating StockBalance ---')

        self.stdout.write('  Building correct balances from all posted documents...')
        correct_bal = _build_balance_from_documents(self._warn)

        self.stdout.write(f'  Computed {len(correct_bal)} (item, location) buckets.')

        # Load all existing balances into a dict for comparison
        existing = {
            (b.item_id, b.location_id): b
            for b in StockBalance.objects.all()
        }

        # All keys to reconcile — None item/location can't map to a DB row so skip them
        all_keys = {
            k for k in (set(correct_bal.keys()) | set(existing.keys()))
            if k[0] is not None and k[1] is not None
        }

        to_create, to_update, unchanged = [], [], 0

        for key in all_keys:
            item_id, loc_id = key
            new_qty = correct_bal.get(key, Decimal('0'))
            bal_obj = existing.get(key)

            if bal_obj is None:
                # Missing balance row — create it (even if qty is zero/negative,
                # so the record exists and future real-time updates work correctly)
                to_create.append(StockBalance(
                    item_id=item_id,
                    location_id=loc_id,
                    qty_on_hand=new_qty,
                    qty_reserved=Decimal('0'),
                ))
                self._info(f'    CREATE item={item_id} loc={loc_id} qty={new_qty}')
            else:
                old_qty = bal_obj.qty_on_hand
                if old_qty != new_qty:
                    self._info(
                        f'    UPDATE item={item_id} loc={loc_id} '
                        f'{old_qty} -> {new_qty}'
                    )
                    bal_obj.qty_on_hand = new_qty
                    to_update.append(bal_obj)
                else:
                    unchanged += 1

        self.stdout.write(
            f'\n  Creates: {len(to_create)}  Updates: {len(to_update)}  '
            f'Unchanged: {unchanged}'
        )

        if not dry_run:
            with transaction.atomic():
                if to_create:
                    StockBalance.objects.bulk_create(to_create)
                if to_update:
                    StockBalance.objects.bulk_update(to_update, ['qty_on_hand'])

            # Sync to changelog + local_cache (bulk ops bypass signals)
            try:
                from sync.signals import bulk_sync_upsert
                all_pks = [b.pk for b in to_create] + [b.pk for b in to_update]
                if all_pks:
                    bulk_sync_upsert(StockBalance, all_pks, source='resync_inventory')
            except Exception as exc:
                self.stdout.write(self.style.WARNING(
                    f'  Sync to changelog failed (non-fatal): {exc}'
                ))

            self.stdout.write(self.style.SUCCESS(
                f'  Committed: {len(to_create)} created, {len(to_update)} updated.'
            ))
            self._resync_summary['changes']['balances_created'] = len(to_create)
            self._resync_summary['changes']['balances_updated'] = len(to_update)
        else:
            self.stdout.write(self.style.WARNING(
                '  (dry-run) No changes written.  Re-run without --dry-run to commit.'
            ))

    # ── Phase 3: Data integrity audit ────────────────────────────────────────

    def _run_phase3(self):
        self.stdout.write('\n--- Phase 3: Data Integrity Audit ---')
        from django.db.models import Count, Q, F
        from catalog.models import Item, UnitConversion, UnitCategory
        from core.models import Invoice

        issues = 0

        # 3a: Negative StockBalance records
        neg = list(StockBalance.objects.filter(qty_on_hand__lt=0).select_related(
            'item', 'location__warehouse'))
        if neg:
            self.stdout.write(self.style.ERROR(
                f'\n  [NEG BALANCE] {len(neg)} item/location(s) have negative stock:'))
            for b in neg[:30]:
                self.stdout.write(self.style.ERROR(
                    f'    item={b.item.code}  loc={b.location}  '
                    f'qty={b.qty_on_hand}'))
            if len(neg) > 30:
                self.stdout.write(self.style.ERROR(
                    f'    ... and {len(neg) - 30} more'))
            issues += len(neg)
            self._resync_summary['changes']['negative_balances'] = len(neg)
        else:
            self.stdout.write(self.style.SUCCESS('  [NEG BALANCE]  none OK'))
            self._resync_summary['changes']['negative_balances'] = 0

        # 3b: Duplicate StockMoves for same (reference_type, reference_id, item)
        dupes = (
            StockMove.objects
            .filter(status=MoveStatus.POSTED)
            .exclude(reference_number__startswith='REV-')
            .exclude(reference_number__startswith='VOID-')
            .values('reference_type', 'reference_id', 'item_id')
            .annotate(cnt=Count('id'))
            .filter(cnt__gt=1)
        )
        dupe_list = list(dupes)
        if dupe_list:
            self.stdout.write(self.style.WARNING(
                f'\n  [DUPE MOVES]  {len(dupe_list)} duplicate move group(s):'))
            for d in dupe_list[:20]:
                self.stdout.write(self.style.WARNING(
                    f'    ref={d["reference_type"]}#{d["reference_id"]}  '
                    f'item={d["item_id"]}  count={d["cnt"]}'))
            issues += len(dupe_list)
        else:
            self.stdout.write(self.style.SUCCESS('  [DUPE MOVES]   none OK'))

        # 3c: StockMoves with unrecognised reference_type
        known_types = set(REFERENCE_TYPE_LOOKUPS.keys())
        unknown_qs = (
            StockMove.objects
            .filter(status=MoveStatus.POSTED)
            .exclude(reference_type__in=known_types)
            .values('reference_type')
            .annotate(cnt=Count('id'))
        )
        unknown_list = list(unknown_qs)
        if unknown_list:
            self.stdout.write(self.style.WARNING(
                f'\n  [UNKNOWN REF] {len(unknown_list)} unrecognised reference_type(s):'))
            for u in unknown_list:
                self.stdout.write(self.style.WARNING(
                    f'    {u["reference_type"]}  ({u["cnt"]} moves)'))
        else:
            self.stdout.write(self.style.SUCCESS('  [UNKNOWN REF]  none OK'))

        # 3d: Items whose current inventory-unit category conflicts with any StockMove unit
        cross_cat_items = set()
        for move in (StockMove.objects
                     .filter(status=MoveStatus.POSTED)
                     .select_related('item__default_unit', 'item__selling_unit', 'unit')
                     .only('item__id', 'unit__category',
                           'item__default_unit__category', 'item__selling_unit__category')):
            stock_cat = _inventory_unit(move.item).category
            if move.unit.category != stock_cat:
                cross_cat_items.add(move.item.code)

        if cross_cat_items:
            self.stdout.write(self.style.WARNING(
                f'\n  [CAT MISMATCH] {len(cross_cat_items)} item(s) have moves in wrong unit category:'))
            for code in sorted(cross_cat_items)[:30]:
                self.stdout.write(self.style.WARNING(f'    {code}'))
            issues += len(cross_cat_items)
        else:
            self.stdout.write(self.style.SUCCESS('  [CAT MISMATCH] none OK'))

        # 3e: Items with selling_unit set but no UnitConversion between default and selling
        conv_missing = []
        for item in Item.objects.filter(
            selling_unit__isnull=False
        ).select_related('default_unit', 'selling_unit').exclude(
            selling_unit=F('default_unit')
        ):
            su = item.selling_unit
            du = item.default_unit
            if su.pk == du.pk:
                continue
            has_conv = UnitConversion.objects.filter(
                Q(from_unit=du, to_unit=su) | Q(from_unit=su, to_unit=du),
                Q(item=item) | Q(item__isnull=True),
                is_active=True,
            ).exists()
            if not has_conv:
                conv_missing.append(f'{item.code}  ({du.abbreviation} <-> {su.abbreviation})')

        if conv_missing:
            self.stdout.write(self.style.WARNING(
                f'\n  [MISSING CONV] {len(conv_missing)} item(s) have selling_unit but no conversion:'))
            for m in conv_missing[:30]:
                self.stdout.write(self.style.WARNING(f'    {m}'))
            issues += len(conv_missing)
        else:
            self.stdout.write(self.style.SUCCESS(
                f'\n  [MISSING CONV] none OK'))

        # 3f: Paid invoices missing COGS (grand_total_cogs null or zero)
        no_cogs_qs = (
            Invoice.objects
            .filter(is_paid=True)
            .filter(Q(grand_total_cogs__isnull=True) | Q(grand_total_cogs=0))
            .exclude(is_void=True)
            .order_by('-date')
        )
        no_cogs_count = no_cogs_qs.count()
        if no_cogs_count:
            self.stdout.write(self.style.WARNING(
                f'\n  [NO COGS] {no_cogs_count} paid invoice(s) have no COGS computed:'))
            for inv in no_cogs_qs.only('invoice_number', 'date', 'grand_total')[:30]:
                self.stdout.write(self.style.WARNING(
                    f'    {inv.invoice_number}  date={inv.date}  '
                    f'total={inv.grand_total}'))
            if no_cogs_count > 30:
                self.stdout.write(self.style.WARNING(
                    f'    ... and {no_cogs_count - 30} more'))
            issues += no_cogs_count
            self._resync_summary['changes']['invoices_no_cogs'] = no_cogs_count
        else:
            self.stdout.write(self.style.SUCCESS('  [NO COGS]      none OK'))
            self._resync_summary['changes']['invoices_no_cogs'] = 0

        # 3g: Catalog items missing selling_unit
        no_selling_qs = (
            Item.objects
            .filter(selling_unit__isnull=True)
            .order_by('code')
        )
        no_selling_count = no_selling_qs.count()
        if no_selling_count:
            self.stdout.write(self.style.WARNING(
                f'\n  [NO SELLING] {no_selling_count} catalog item(s) have no selling_unit:'))
            for it in no_selling_qs.only('code', 'name')[:30]:
                self.stdout.write(self.style.WARNING(
                    f'    {it.code}  {it.name}'))
            if no_selling_count > 30:
                self.stdout.write(self.style.WARNING(
                    f'    ... and {no_selling_count - 30} more'))
            issues += no_selling_count
            self._resync_summary['changes']['items_no_selling_unit'] = no_selling_count
        else:
            self.stdout.write(self.style.SUCCESS('  [NO SELLING]   none OK'))
            self._resync_summary['changes']['items_no_selling_unit'] = 0

        # Record cumulative integrity issues
        self._resync_summary['changes']['integrity_issues'] = issues

        # Summary
        if issues:
            self.stdout.write(self.style.ERROR(
                f'\n  Phase 3 total: {issues} issue(s) found - see above for details.'))
        else:
            self.stdout.write(self.style.SUCCESS(
                f'\n  Phase 3: all integrity checks passed OK'))
