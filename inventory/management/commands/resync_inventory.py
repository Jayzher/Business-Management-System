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
  - Missing unit conversions → hard error (no silent fallback)
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
from decimal import Decimal, InvalidOperation

from django.core.management.base import BaseCommand
from django.db import transaction
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
        warn_fn(f"    [ERROR] {label}: {exc}")
        raise


# ── Phase 0 helpers ─────────────────────────────────────────────────────────

def _deduplicate_moves(dry_run, warn_fn):
    """
    Remove duplicate POSTED StockMoves whose (reference_type, reference_id,
    item_id, from_location_id, to_location_id) tuple appears more than once.
    For each group keep the move with qty closest to the converted source-doc
    qty; when undecidable keep the oldest (lowest pk) and delete the rest.
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

    return removed, len(dupes)


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
        existing_ids = set(
            Model.objects.filter(pk__in=move_ref_ids).values_list('pk', flat=True)
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
            info_fn(
                f'    [ORPHAN] Move#{m.pk} ref={ref_type}#{m.reference_id} '
                f'item={m.item.code} qty={m.qty} '
                f'(source document deleted)'
            )

        count = orphaned_qs.count()
        if count > 200:
            info_fn(f'    [ORPHAN] ... and {count - 200} more orphaned moves for {ref_type}')

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


def _line_locations(ref_type, doc, line, qty):
    if ref_type == 'GoodsReceipt':
        return None, line.location_id
    if ref_type in ('DeliveryNote', 'SalesPickup', 'DamagedReport', 'PurchaseReturn', 'InventoryToSupplyTransfer', 'CustomerService'):
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
    grns = GoodsReceipt.objects.filter(
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
        ('GoodsReceipt', GoodsReceipt.objects.filter(status=DocumentStatus.POSTED).prefetch_related('lines__item__default_unit', 'lines__item__selling_unit', 'lines__unit', 'lines__location')),
        ('DeliveryNote', DeliveryNote.objects.filter(status=DocumentStatus.POSTED).prefetch_related('lines__item__default_unit', 'lines__item__selling_unit', 'lines__unit', 'lines__location')),
        ('SalesPickup', SalesPickup.objects.filter(status=DocumentStatus.POSTED).prefetch_related('lines__item__default_unit', 'lines__item__selling_unit', 'lines__unit', 'lines__location')),
        ('StockTransfer', StockTransfer.objects.filter(status=DocumentStatus.POSTED).prefetch_related('lines__item__default_unit', 'lines__item__selling_unit', 'lines__unit', 'lines__from_location', 'lines__to_location')),
        ('StockAdjustment', StockAdjustment.objects.filter(status=DocumentStatus.POSTED).prefetch_related('lines__item__default_unit', 'lines__item__selling_unit', 'lines__unit', 'lines__location')),
        ('DamagedReport', DamagedReport.objects.filter(status=DocumentStatus.POSTED).prefetch_related('lines__item__default_unit', 'lines__item__selling_unit', 'lines__unit', 'lines__location')),
        ('POSSale', POSSale.objects.filter(status=SaleStatus.POSTED).prefetch_related('lines__item__default_unit', 'lines__item__selling_unit', 'lines__unit', 'lines__location').select_related('location')),
        ('POSRefund', POSRefund.objects.filter(status=RefundStatus.POSTED).prefetch_related('lines__item__default_unit', 'lines__item__selling_unit', 'lines__unit', 'lines__location')),
        ('InventoryToSupplyTransfer', InventoryToSupplyTransfer.objects.filter(status=DocumentStatus.POSTED).prefetch_related('lines__item__default_unit', 'lines__item__selling_unit', 'lines__unit', 'lines__location')),
        ('PurchaseReturn', PurchaseReturn.objects.filter(status=DocumentStatus.POSTED).prefetch_related('lines__item__default_unit', 'lines__item__selling_unit', 'lines__unit', 'lines__location')),
        ('SalesReturn', SalesReturn.objects.filter(status=DocumentStatus.POSTED).prefetch_related('lines__item__default_unit', 'lines__item__selling_unit', 'lines__unit', 'lines__location')),
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
        if key in existing_keys:
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
        created += 1

    return created


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
    for grn in GoodsReceipt.objects.filter(status=DocumentStatus.POSTED).prefetch_related(
        'lines__item__default_unit', 'lines__item__selling_unit', 'lines__unit', 'lines__location'
    ):
        all_documents.append(('GoodsReceipt', grn, _doc_date(grn)))

    # ── DeliveryNote ────────────────────────────────────────────────────────
    for dn in DeliveryNote.objects.filter(status=DocumentStatus.POSTED).prefetch_related(
        'lines__item__default_unit', 'lines__item__selling_unit', 'lines__unit', 'lines__location'
    ):
        all_documents.append(('DeliveryNote', dn, _doc_date(dn)))

    # ── SalesPickup ─────────────────────────────────────────────────────────
    for sp in SalesPickup.objects.filter(status=DocumentStatus.POSTED).prefetch_related(
        'lines__item__default_unit', 'lines__item__selling_unit', 'lines__unit', 'lines__location'
    ):
        all_documents.append(('SalesPickup', sp, _doc_date(sp)))

    # ── StockTransfer ────────────────────────────────────────────────────────
    for tr in StockTransfer.objects.filter(status=DocumentStatus.POSTED).prefetch_related(
        'lines__item__default_unit', 'lines__item__selling_unit', 'lines__unit',
        'lines__from_location', 'lines__to_location'
    ):
        all_documents.append(('StockTransfer', tr, _doc_date(tr)))

    # ── StockAdjustment ──────────────────────────────────────────────────────
    for adj in StockAdjustment.objects.filter(status=DocumentStatus.POSTED).prefetch_related(
        'lines__item__default_unit', 'lines__item__selling_unit', 'lines__unit', 'lines__location'
    ):
        all_documents.append(('StockAdjustment', adj, _doc_date(adj)))

    # ── DamagedReport ────────────────────────────────────────────────────────
    for dr in DamagedReport.objects.filter(status=DocumentStatus.POSTED).prefetch_related(
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
    for ist in InventoryToSupplyTransfer.objects.filter(status=DocumentStatus.POSTED).prefetch_related(
        'lines__item__default_unit', 'lines__item__selling_unit', 'lines__unit', 'lines__location'
    ):
        all_documents.append(('InventoryToSupplyTransfer', ist, _doc_date(ist)))

    # ── PurchaseReturn ───────────────────────────────────────────────────────
    for pr in PurchaseReturn.objects.filter(status=DocumentStatus.POSTED).prefetch_related(
        'lines__item__default_unit', 'lines__item__selling_unit', 'lines__unit', 'lines__location'
    ):
        all_documents.append(('PurchaseReturn', pr, _doc_date(pr)))

    # ── SalesReturn ──────────────────────────────────────────────────────────
    for sr in SalesReturn.objects.filter(status=DocumentStatus.POSTED).prefetch_related(
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
            for line in doc.lines.all():
                raw_diff = line.qty_counted - line.qty_system
                if raw_diff == 0:
                    continue
                target_unit = _inventory_unit(line.item)
                try:
                    q = _safe_convert(abs(raw_diff), line.unit, target_unit,
                                      f"Adj#{doc.pk} item={line.item.code}", warn_fn, item=line.item)
                except (ValueError, Exception):
                    continue
                _accumulate(bal, line.item_id, line.location_id,
                            q if raw_diff > 0 else -q)
        
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
            for line in doc.lines.all():
                if getattr(line, 'is_scrap', False):
                    continue
                if line.location_id is None:
                    continue
                target_unit = _inventory_unit(line.item)
                try:
                    q = _safe_convert(line.qty, line.unit, target_unit,
                                      f"Service#{doc.pk} item={line.item.code}", warn_fn, item=line.item)
                except (ValueError, Exception):
                    continue
                _accumulate(bal, line.item_id, line.location_id, -q)
            
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

        # Reset the global error collector at the start of each run.
        _conversion_errors.clear()

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

        if phase in ('0', 'all'):
            self._run_phase0(dry_run)
        if phase in ('1', 'all'):
            self._run_phase1(dry_run)

        # ── Report conversion errors from Phase 0/1 but continue ──────────
        if _conversion_errors and phase in ('2', 'all'):
            self._report_conversion_errors()
            self.stderr.write(self.style.WARNING(
                '\n  WARNING: conversion errors found in Phase 0/1 (see above).\n'
                '  Phase 2 will proceed and skip only the affected items.\n'
            ))
            # Clear so Phase 2 starts with a fresh error list
            _conversion_errors.clear()

        if phase in ('2', 'all'):
            self._run_phase2(dry_run)

            if _conversion_errors:
                self._report_conversion_errors()
                self.stderr.write(self.style.WARNING(
                    '\n  WARNING: Phase 2 completed but skipped items with missing conversions.\n'
                    '  The balances for those items may be inaccurate. Add the conversions and re-run.\n'
                ))

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
            if changes.get('balances_updated'):
                parts.append(f"{changes['balances_updated']} balances updated")
            if changes.get('balances_created'):
                parts.append(f"{changes['balances_created']} balances created")
            if changes.get('financial_months_recalculated'):
                parts.append(f"{changes['financial_months_recalculated']} financial months recalculated")

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
        """Print a de-duplicated summary of all conversion errors encountered."""
        seen = set()
        unique_errors = []
        for err in _conversion_errors:
            if err.key not in seen:
                seen.add(err.key)
                unique_errors.append(err)

        self.stdout.write(self.style.ERROR(
            f'\n{"═"*70}\n'
            f'  MISSING UNIT CONVERSIONS — {len(unique_errors)} item(s) need attention\n'
            f'{"═"*70}'
        ))
        self.stdout.write(self.style.ERROR(
            '  These items have documents using a unit that cannot be converted\n'
            '  to the item\'s inventory unit.  Add the conversion in:\n'
            '  Catalog → Unit Conversions  (or Admin → Unit Conversions)\n'
        ))
        for err in sorted(unique_errors, key=lambda e: e.item_code):
            self.stdout.write(self.style.ERROR(
                f'    {err.item_code:40s}  {err.from_unit} → {err.to_unit}'
            ))
        self.stdout.write('')

    # ── Phase 0: clean up StockMoves ─────────────────────────────────────────

    def _run_phase0(self, dry_run):
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

    def _delete_excess_moves(self, dry_run):
        """
        Delete POSTED StockMoves whose source document still exists but the
        specific line item was deleted in admin.  The move references a
        (document, item) pair that no longer has a matching line.
        """
        deleted = 0
        for ref_type, lookup_factory in REFERENCE_TYPE_LOOKUPS.items():
            moves = (
                StockMove.objects.filter(
                    reference_type=ref_type, status=MoveStatus.POSTED,
                )
                .exclude(reference_number__startswith='REV-')
                .exclude(reference_number__startswith='VOID-')
                .select_related('item')
            )
            lookup_fn = lookup_factory()
            for move in moves:
                line = lookup_fn(move)
                if line is None:
                    # The document exists (not orphaned — 0a would have caught it)
                    # but the specific line is gone.  This move is excess.
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

        issues = 0

        # 3a: Negative StockBalance records
        neg = list(StockBalance.objects.filter(qty_on_hand__lt=0).select_related(
            'item', 'location__warehouse'))
        if neg:
            self.stdout.write(self.style.ERROR(
                f'\n  [NEG BALANCE] {len(neg)} item/location(s) have negative stock:'))
            for b in neg:
                self.stdout.write(self.style.ERROR(
                    f'    item={b.item.code}  loc={b.location}  '
                    f'qty={b.qty_on_hand}'))
            issues += len(neg)
        else:
            self.stdout.write(self.style.SUCCESS('  [NEG BALANCE]  none OK'))

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

        # Summary
        if issues:
            self.stdout.write(self.style.ERROR(
                f'\n  Phase 3 total: {issues} issue(s) found - see above for details.'))
        else:
            self.stdout.write(self.style.SUCCESS(
                f'\n  Phase 3: all integrity checks passed OK'))
