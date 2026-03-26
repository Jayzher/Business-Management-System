"""
Management command: resync_inventory
======================================
Re-synchronises StockBalance and StockMove records to reflect correct unit
conversion using each item's current default_unit / selling_unit setup.

Before this command was available, some posting services stored RAW line.qty
in StockMoves without converting to the item's current inventory unit
(selling_unit when set, otherwise default_unit).  As a result:
  - StockBalance was wrong whenever a document line used a different unit
    (e.g. selling 3 boxes when inventory unit=pcs and 1 box=20 pcs stored -3
    instead of -60).

The command does two independent phases:

  Phase 1 — Fix StockMove.qty
    For every POSTED StockMove linked to a source document line, recompute
    qty into the item's current inventory unit derived from selling_unit /
    default_unit, then update the row.  Reversal moves (created by
    cancel_document) are updated to mirror their corrected originals.

  Phase 2 — Recalculate StockBalance from scratch
    Zeros all StockBalance records, then walks every POSTED document in order
    (GRN → DN → Pickup → Transfer → Adjustment → Damaged → POS → Refund →
     IST → PurchaseReturn → SalesReturn) and accumulates the correct base-unit
    delta per (item, location) bucket.  CANCELLED documents are skipped
    (their reversal moves cancel out).  At the end, bulk-updates StockBalance.

Usage:
    python manage.py resync_inventory                  # applies changes by default
    python manage.py resync_inventory --dry-run        # preview without saving
    python manage.py resync_inventory --phase 1        # moves only (applies)
    python manage.py resync_inventory --phase 2 --dry-run
    python manage.py resync_inventory --quiet          # no per-row output
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
    """Return the canonical resync unit for inventory rebuilding.

    Uses item.stock_unit (selling_unit when set, else default_unit) to match
    the unit in which all posting services store StockMoves and StockBalances.
    """
    return item.stock_unit


def _safe_convert(qty, from_unit, to_unit, label, warn_fn, item=None):
    """convert_to_base_unit with graceful fallback: log warning and return raw qty."""
    try:
        return convert_to_base_unit(qty, from_unit, to_unit, item=item)
    except (ValueError, Exception) as exc:
        target_label = getattr(to_unit, 'abbreviation', str(to_unit)) if to_unit is not None else 'N/A'
        warn_fn(f"    [WARN] {label}: {exc}  -> using raw qty={qty} in target_unit={target_label}")
        return qty


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
        'CustomerService': MoveType.DELIVER,
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
        ('CustomerService', CustomerService.objects.filter(status=ServiceStatus.COMPLETED).prefetch_related('lines__item__default_unit', 'lines__item__selling_unit', 'lines__unit', 'lines__location')),
    ]

    for ref_type, docs in doc_specs:
        for doc in docs:
            for line in doc.lines.all():
                qty = _line_qty(ref_type, line, warn_fn)
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
                base_qty = _safe_convert(
                    qty, pli.unit, target_unit,
                    f"POSSale#{sale.pk} bundle={bundle_line.price_list.name} item={item.code}",
                    warn_fn, item=item,
                )
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
    from services.models import ServiceLine
    cache = {}
    def lookup(move):
        key = (move.reference_id, move.item_id)
        if key not in cache:
            cache[key] = ServiceLine.objects.filter(
                service_id=move.reference_id, item_id=move.item_id
            ).select_related('unit').first()
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
    Walk every POSTED document, apply correct base-unit conversion, accumulate
    (item, location) → qty_on_hand delta.  Returns a defaultdict.
    """
    from procurement.models import GoodsReceipt, PurchaseReturn
    from sales.models import DeliveryNote, SalesPickup, SalesReturn
    from inventory.models import StockTransfer, StockAdjustment, DamagedReport, InventoryToSupplyTransfer
    from pos.models import POSSale, POSRefund, SaleStatus, RefundStatus

    bal = defaultdict(Decimal)

    # ── GoodsReceipt ────────────────────────────────────────────────────────
    for grn in GoodsReceipt.objects.filter(status=DocumentStatus.POSTED).prefetch_related(
        'lines__item__default_unit', 'lines__item__selling_unit', 'lines__unit', 'lines__location'
    ):
        for line in grn.lines.all():
            target_unit = _inventory_unit(line.item)
            q = _safe_convert(line.qty, line.unit, target_unit,
                              f"GRN#{grn.pk} item={line.item.code}", warn_fn, item=line.item)
            _accumulate(bal, line.item_id, line.location_id, q)

    # ── DeliveryNote ────────────────────────────────────────────────────────
    for dn in DeliveryNote.objects.filter(status=DocumentStatus.POSTED).prefetch_related(
        'lines__item__default_unit', 'lines__item__selling_unit', 'lines__unit', 'lines__location'
    ):
        for line in dn.lines.all():
            target_unit = _inventory_unit(line.item)
            q = _safe_convert(line.qty, line.unit, target_unit,
                              f"DN#{dn.pk} item={line.item.code}", warn_fn, item=line.item)
            _accumulate(bal, line.item_id, line.location_id, -q)

    # ── SalesPickup ─────────────────────────────────────────────────────────
    for sp in SalesPickup.objects.filter(status=DocumentStatus.POSTED).prefetch_related(
        'lines__item__default_unit', 'lines__item__selling_unit', 'lines__unit', 'lines__location'
    ):
        for line in sp.lines.all():
            target_unit = _inventory_unit(line.item)
            q = _safe_convert(line.qty, line.unit, target_unit,
                              f"Pickup#{sp.pk} item={line.item.code}", warn_fn, item=line.item)
            _accumulate(bal, line.item_id, line.location_id, -q)

    # ── StockTransfer ────────────────────────────────────────────────────────
    for tr in StockTransfer.objects.filter(status=DocumentStatus.POSTED).prefetch_related(
        'lines__item__default_unit', 'lines__item__selling_unit', 'lines__unit',
        'lines__from_location', 'lines__to_location'
    ):
        for line in tr.lines.all():
            target_unit = _inventory_unit(line.item)
            q = _safe_convert(line.qty, line.unit, target_unit,
                              f"Transfer#{tr.pk} item={line.item.code}", warn_fn, item=line.item)
            _accumulate(bal, line.item_id, line.from_location_id, -q)
            _accumulate(bal, line.item_id, line.to_location_id, q)

    # ── StockAdjustment ──────────────────────────────────────────────────────
    for adj in StockAdjustment.objects.filter(status=DocumentStatus.POSTED).prefetch_related(
        'lines__item__default_unit', 'lines__item__selling_unit', 'lines__unit', 'lines__location'
    ):
        for line in adj.lines.all():
            raw_diff = line.qty_counted - line.qty_system
            if raw_diff == 0:
                continue
            target_unit = _inventory_unit(line.item)
            q = _safe_convert(abs(raw_diff), line.unit, target_unit,
                              f"Adj#{adj.pk} item={line.item.code}", warn_fn, item=line.item)
            _accumulate(bal, line.item_id, line.location_id,
                        q if raw_diff > 0 else -q)

    # ── DamagedReport ────────────────────────────────────────────────────────
    for dr in DamagedReport.objects.filter(status=DocumentStatus.POSTED).prefetch_related(
        'lines__item__default_unit', 'lines__item__selling_unit', 'lines__unit', 'lines__location'
    ):
        for line in dr.lines.all():
            target_unit = _inventory_unit(line.item)
            q = _safe_convert(line.qty, line.unit, target_unit,
                              f"Damaged#{dr.pk} item={line.item.code}", warn_fn, item=line.item)
            _accumulate(bal, line.item_id, line.location_id, -q)

    # ── POSSale ──────────────────────────────────────────────────────────────
    for sale in POSSale.objects.filter(status=SaleStatus.POSTED).prefetch_related(
        'lines__item__default_unit', 'lines__item__selling_unit', 'lines__unit', 'lines__location',
        'bundle_lines__price_list__items__item__default_unit',
        'bundle_lines__price_list__items__item__selling_unit',
        'bundle_lines__price_list__items__item__stock_unit',
        'bundle_lines__price_list__items__unit',
    ).select_related('location'):
        for line in sale.lines.all():
            loc_id = line.location_id or sale.location_id
            target_unit = _inventory_unit(line.item)
            q = _safe_convert(line.qty, line.unit, target_unit,
                              f"POSSale#{sale.pk} item={line.item.code}", warn_fn, item=line.item)
            _accumulate(bal, line.item_id, loc_id, -q)

        # Bundle component deductions — each bundle set consumes its component items
        for bundle_line in sale.bundle_lines.all():
            for pli in bundle_line.price_list.items.all():
                item = pli.item
                qty = pli.min_qty * bundle_line.qty_sets
                if qty <= Decimal('0'):
                    continue
                target_unit = _inventory_unit(item)
                q = _safe_convert(qty, pli.unit, target_unit,
                                  f"POSSale#{sale.pk} bundle={bundle_line.price_list.name} item={item.code}",
                                  warn_fn, item=item)
                _accumulate(bal, item.pk, sale.location_id, -q)

    # ── POSRefund ────────────────────────────────────────────────────────────
    for refund in POSRefund.objects.filter(status=RefundStatus.POSTED).prefetch_related(
        'lines__item__default_unit', 'lines__item__selling_unit', 'lines__unit', 'lines__location'
    ):
        for line in refund.lines.all():
            target_unit = _inventory_unit(line.item)
            q = _safe_convert(line.qty, line.unit, target_unit,
                              f"POSRefund#{refund.pk} item={line.item.code}", warn_fn, item=line.item)
            _accumulate(bal, line.item_id, line.location_id, q)

    # ── InventoryToSupplyTransfer ────────────────────────────────────────────
    for ist in InventoryToSupplyTransfer.objects.filter(status=DocumentStatus.POSTED).prefetch_related(
        'lines__item__default_unit', 'lines__item__selling_unit', 'lines__unit', 'lines__location'
    ):
        for line in ist.lines.all():
            target_unit = _inventory_unit(line.item)
            q = _safe_convert(line.qty, line.unit, target_unit,
                              f"IST#{ist.pk} item={line.item.code}", warn_fn, item=line.item)
            _accumulate(bal, line.item_id, line.location_id, -q)

    # ── PurchaseReturn ───────────────────────────────────────────────────────
    for pr in PurchaseReturn.objects.filter(status=DocumentStatus.POSTED).prefetch_related(
        'lines__item__default_unit', 'lines__item__selling_unit', 'lines__unit', 'lines__location'
    ):
        for line in pr.lines.all():
            target_unit = _inventory_unit(line.item)
            q = _safe_convert(line.qty, line.unit, target_unit,
                              f"PurchReturn#{pr.pk} item={line.item.code}", warn_fn, item=line.item)
            _accumulate(bal, line.item_id, line.location_id, -q)

    # ── SalesReturn ──────────────────────────────────────────────────────────
    for sr in SalesReturn.objects.filter(status=DocumentStatus.POSTED).prefetch_related(
        'lines__item__default_unit', 'lines__item__selling_unit', 'lines__unit', 'lines__location'
    ):
        for line in sr.lines.all():
            target_unit = _inventory_unit(line.item)
            q = _safe_convert(line.qty, line.unit, target_unit,
                              f"SalesReturn#{sr.pk} item={line.item.code}", warn_fn, item=line.item)
            _accumulate(bal, line.item_id, line.location_id, q)

    # ── CustomerService ──────────────────────────────────────────────────────
    from services.models import CustomerService, ServiceStatus
    for svc in CustomerService.objects.filter(status=ServiceStatus.COMPLETED).prefetch_related(
        'lines__item__default_unit', 'lines__item__selling_unit', 'lines__unit', 'lines__location'
    ):
        for line in svc.lines.all():
            if line.location_id is None:
                continue
            target_unit = _inventory_unit(line.item)
            q = _safe_convert(line.qty, line.unit, target_unit,
                              f"Service#{svc.pk} item={line.item.code}", warn_fn, item=line.item)
            _accumulate(bal, line.item_id, line.location_id, -q)

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
            choices=['0', '1', '2', '3', 'all'],
            default='all',
            help='0=dedup moves, 1=fix qtys, 2=recalc balances, 3=audit, all=all (default).',
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
        if phase in ('2', 'all'):
            self._run_phase2(dry_run)
        if phase in ('3', 'all'):
            self._run_phase3()

        self.stdout.write(self.style.SUCCESS('\n=== Done ===\n'))

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

    # ── Phase 1: fix StockMove.qty ───────────────────────────────────────────

    def _run_phase1(self, dry_run):
        self.stdout.write('\n--- Phase 1: Correcting StockMove quantities ---')

        total_stats = {'updated': 0, 'already_correct': 0, 'no_line': 0, 'backfilled': 0}

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
            stats = {'updated': 0, 'already_correct': 0, 'no_line': 0}
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
