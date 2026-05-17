"""
Inventory posting engine — the core business logic.
All stock changes go through this service to ensure consistency.
"""
import logging
from decimal import Decimal
from django.db import transaction
from django.utils import timezone

from inventory.models import (
    StockMove, StockBalance, MoveType, MoveStatus,
    StockTransfer, StockAdjustment, DamagedReport,
)
from audit.models import AuditLog
from catalog.models import convert_to_base_unit

logger = logging.getLogger(__name__)


def _try_convert(qty, from_unit, to_unit, item, line, skipped):
    """Attempt unit conversion; on failure record the skip and return None.

    *skipped* is a list that collects dicts describing each incompatible
    line so the caller can report them after posting.
    """
    try:
        return convert_to_base_unit(qty, from_unit, to_unit, item=item)
    except (ValueError, Exception) as exc:
        skipped.append({
            'item_code': item.code,
            'item_name': item.name,
            'line_qty': qty,
            'line_unit': getattr(from_unit, 'abbreviation', str(from_unit)),
            'stock_unit': getattr(to_unit, 'abbreviation', str(to_unit)),
            'error': str(exc),
        })
        logger.warning(
            'Skipping line %s x%s %s → %s: %s',
            item.code, qty,
            getattr(from_unit, 'abbreviation', from_unit),
            getattr(to_unit, 'abbreviation', to_unit),
            exc,
        )
        return None


def format_skipped_lines_message(doc, doc_label=None):
    """Build a user-facing warning string from ``doc.skipped_lines``.

    Returns an empty string when nothing was skipped.  Views can call
    this after any post_* function and pass the result to
    ``messages.warning()`` if non-empty.
    """
    skipped = getattr(doc, 'skipped_lines', None)
    if not skipped:
        return ''
    label = doc_label or getattr(doc, 'document_number', str(doc))
    items = ', '.join(
        f"{s['item_code']} ({s['line_qty']} {s['line_unit']} → {s['stock_unit']})"
        for s in skipped
    )
    return (
        f'{label} posted but {len(skipped)} line(s) skipped due to '
        f'incompatible units: {items}. '
        f'Add the missing Unit Conversions under Catalog → Unit Conversions.'
    )


def _update_balance(item, location, qty_delta, reserved_delta=Decimal('0')):
    """
    Atomically update (or create) a StockBalance row.
    Uses select_for_update to prevent race conditions.
    """
    balance, created = StockBalance.objects.select_for_update().get_or_create(
        item=item,
        location=location,
        defaults={'qty_on_hand': Decimal('0'), 'qty_reserved': Decimal('0')},
    )
    balance.qty_on_hand += qty_delta
    balance.qty_reserved += reserved_delta

    # Check negative stock
    warehouse = location.warehouse
    if not warehouse.allow_negative_stock and balance.qty_on_hand < 0:
        raise ValueError(
            f"Insufficient stock for {item.code} at {location}. "
            f"Available: {balance.qty_on_hand - qty_delta}, Requested: {abs(qty_delta)}"
        )

    balance.save()
    return balance


def _create_audit(user, action, obj, changes=None):
    """Create a rich audit log entry with automatic detail extraction."""
    details = changes or {}

    # ── Auto-extract document details ────────────────────────────────
    doc_number = (
        getattr(obj, 'document_number', None)
        or getattr(obj, 'sale_no', None)
        or getattr(obj, 'refund_no', None)
        or getattr(obj, 'service_number', None)
        or ''
    )
    if doc_number:
        details['document_number'] = doc_number

    status = getattr(obj, 'status', None)
    if status:
        details['status'] = str(status)

    # Extract line items summary for documents that have lines
    if hasattr(obj, 'lines') and action in ('POST', 'CANCEL', 'APPROVE', 'CREATE'):
        try:
            lines_data = []
            total_qty = Decimal('0')
            total_value = Decimal('0')
            for line in obj.lines.select_related('item', 'unit').all()[:20]:
                item_code = getattr(line.item, 'code', '?')
                qty = getattr(line, 'qty', None) or getattr(line, 'qty_ordered', None) or Decimal('0')
                unit_abbr = getattr(line.unit, 'abbreviation', '') if hasattr(line, 'unit') and line.unit else ''
                line_total = getattr(line, 'line_total', None)

                entry = {'item': item_code, 'qty': str(qty)}
                if unit_abbr:
                    entry['unit'] = unit_abbr
                if line_total is not None:
                    entry['value'] = str(line_total)
                    total_value += Decimal(str(line_total))
                lines_data.append(entry)
                total_qty += Decimal(str(qty))

            details['line_count'] = len(lines_data)
            details['total_qty'] = str(total_qty)
            if total_value:
                details['total_value'] = str(total_value)
            if lines_data:
                details['items'] = lines_data
        except Exception:
            pass

    # Extract financial totals
    for field in ('grand_total', 'subtotal', 'total', 'amount', 'delivery_charge'):
        val = getattr(obj, field, None)
        if val is not None and field not in details:
            details[field] = str(val)

    # Extract related entities
    supplier = getattr(obj, 'supplier', None)
    if supplier:
        details['supplier'] = str(supplier.name) if hasattr(supplier, 'name') else str(supplier)
    customer = getattr(obj, 'customer', None)
    if customer:
        details['customer'] = str(customer.name) if hasattr(customer, 'name') else str(customer)
    warehouse = getattr(obj, 'warehouse', None)
    if warehouse:
        details['warehouse'] = str(warehouse.name) if hasattr(warehouse, 'name') else str(warehouse)

    # Extract linked documents
    so = getattr(obj, 'sales_order', None)
    if so:
        details['sales_order'] = getattr(so, 'document_number', str(so))
    po = getattr(obj, 'purchase_order', None)
    if po:
        details['purchase_order'] = getattr(po, 'document_number', str(po))

    AuditLog.objects.create(
        user=user,
        action=action,
        model_name=obj.__class__.__name__,
        object_id=obj.pk,
        object_repr=str(obj)[:255],
        changes=details,
    )


@transaction.atomic
def post_goods_receipt(grn, user):
    """
    Post a GRN: creates RECEIVE StockMoves and updates balances.

    Lines whose unit is incompatible with the item's stock_unit (no
    UnitConversion exists) are **skipped** — they do not block the rest
    of the GRN from posting.  The returned object carries a
    ``skipped_lines`` attribute (list of dicts) describing every line
    that was skipped so the caller / view can display them.
    """
    from procurement.models import GoodsReceipt
    from core.models import DocumentStatus

    if grn.status != DocumentStatus.DRAFT:
        raise ValueError(f"GRN {grn.document_number} is not in DRAFT status.")

    now = timezone.now()
    moves = []
    skipped = []

    for line in grn.lines.select_related('item__default_unit', 'item__selling_unit', 'unit').all():
        base_qty = _try_convert(line.qty, line.unit, line.item.stock_unit, line.item, line, skipped)
        if base_qty is None:
            continue

        move = StockMove(
            move_type=MoveType.RECEIVE,
            item=line.item,
            qty=base_qty,
            unit=line.item.stock_unit,
            from_location=None,
            to_location=line.location,
            reference_type='GoodsReceipt',
            reference_id=grn.pk,
            reference_number=grn.document_number,
            batch_number=line.batch_number,
            serial_number=line.serial_number,
            status=MoveStatus.POSTED,
            created_by=user,
            posted_by=user,
            posted_at=now,
        )
        moves.append(move)
        _update_balance(line.item, line.location, base_qty)

        # Update PO received qty if linked
        if grn.purchase_order:
            po_lines = grn.purchase_order.lines.filter(item=line.item)
            for po_line in po_lines:
                po_line.qty_received += line.qty
                po_line.save(update_fields=['qty_received'])

    StockMove.objects.bulk_create(moves)

    # Weighted average cost update (includes proportional delivery charge)
    from catalog.models import Item
    delivery_charge = grn.delivery_charge or Decimal('0')
    grn_lines = list(grn.lines.select_related('item').all())

    # Calculate total line value to distribute delivery charge proportionally
    line_values = {}
    total_line_value = Decimal('0')
    for line in grn_lines:
        po_unit_price = Decimal('0')
        if grn.purchase_order:
            po_line = grn.purchase_order.lines.filter(item=line.item).first()
            if po_line:
                po_unit_price = po_line.unit_price
        lv = line.qty * po_unit_price
        line_values[line.pk] = {'po_unit_price': po_unit_price, 'line_value': lv}
        total_line_value += lv

    for line in grn_lines:
        item = line.item
        if item.cost_price is None:
            item.cost_price = Decimal('0')
        total_existing_qty = sum(
            b.qty_on_hand for b in StockBalance.objects.filter(item=item)
        )
        # total_existing_qty already includes the qty we just added
        old_qty = total_existing_qty - line.qty
        if old_qty + line.qty > 0:
            po_unit_price = line_values[line.pk]['po_unit_price']
            # Distribute delivery charge proportionally by line value
            line_delivery_share = Decimal('0')
            if delivery_charge > 0 and total_line_value > 0:
                line_delivery_share = delivery_charge * (line_values[line.pk]['line_value'] / total_line_value)
            elif delivery_charge > 0 and len(grn_lines) > 0:
                # Equal split if no PO prices available
                line_delivery_share = delivery_charge / len(grn_lines)
            landed_unit_price = po_unit_price + (line_delivery_share / line.qty if line.qty else Decimal('0'))
            if landed_unit_price > 0:
                old_value = old_qty * item.cost_price
                new_value = line.qty * landed_unit_price
                item.cost_price = (old_value + new_value) / (old_qty + line.qty)
                item.save(update_fields=['cost_price', 'updated_at'])

    grn.status = DocumentStatus.POSTED
    grn.posted_by = user
    grn.posted_at = now
    grn.save(update_fields=['status', 'posted_by', 'posted_at', 'updated_at'])

    _create_audit(user, 'POST', grn, {
        'lines': len(moves),
        'skipped_lines': len(skipped),
    })
    grn.skipped_lines = skipped
    return grn


def _ensure_so_bundle_lines_on_delivery(delivery):
    """
    If the Delivery Note is linked to a Sales Order that has bundle lines
    (SalesOrderPriceListLine), ensure every bundle component item appears
    in the DN lines.  Missing items are added automatically so that posting
    deducts stock for the full order including bundles.

    Idempotent: items already present in DN lines are skipped.
    """
    from sales.models import DeliveryLine
    from warehouses.models import Location

    so = delivery.sales_order
    if so is None:
        return

    bundles = so.price_list_lines.select_related('price_list').prefetch_related(
        'price_list__items__item', 'price_list__items__unit'
    ).all()
    if not bundles:
        return

    # Items already in DN lines
    existing_items = set(
        delivery.lines.values_list('item_id', flat=True)
    )

    # Default location for new lines
    default_location = Location.objects.filter(
        warehouse=delivery.warehouse, is_pickable=True, is_active=True
    ).order_by('code').first()
    if not default_location:
        default_location = Location.objects.filter(
            warehouse=delivery.warehouse, is_active=True
        ).first()
    if not default_location:
        return  # cannot add lines without a location

    for bundle in bundles:
        for pli in bundle.price_list.items.select_related('item', 'unit').all():
            qty = pli.min_qty * bundle.qty_multiplier
            if qty <= 0:
                continue
            if pli.item_id in existing_items:
                continue  # already in DN lines
            DeliveryLine.objects.create(
                delivery=delivery,
                item=pli.item,
                location=default_location,
                qty=qty,
                unit=pli.unit,
                notes=f'Auto-added from bundle: {bundle.price_list.name}',
            )
            existing_items.add(pli.item_id)


def _ensure_so_bundle_lines_on_pickup(pickup):
    """
    If the Sales Pickup is linked to a Sales Order that has bundle lines
    (SalesOrderPriceListLine), ensure every bundle component item appears
    in the Pickup lines.  Missing items are added automatically so that
    posting deducts stock for the full order including bundles.

    Idempotent: items already present in Pickup lines are skipped.
    """
    from sales.models import SalesPickupLine
    from warehouses.models import Location

    so = pickup.sales_order
    if so is None:
        return

    bundles = so.price_list_lines.select_related('price_list').prefetch_related(
        'price_list__items__item', 'price_list__items__unit'
    ).all()
    if not bundles:
        return

    existing_items = set(
        pickup.lines.values_list('item_id', flat=True)
    )

    default_location = Location.objects.filter(
        warehouse=pickup.warehouse, is_pickable=True, is_active=True
    ).order_by('code').first()
    if not default_location:
        default_location = Location.objects.filter(
            warehouse=pickup.warehouse, is_active=True
        ).first()
    if not default_location:
        return

    for bundle in bundles:
        for pli in bundle.price_list.items.select_related('item', 'unit').all():
            qty = pli.min_qty * bundle.qty_multiplier
            if qty <= 0:
                continue
            if pli.item_id in existing_items:
                continue
            SalesPickupLine.objects.create(
                pickup=pickup,
                item=pli.item,
                location=default_location,
                qty=qty,
                unit=pli.unit,
                notes=f'Auto-added from bundle: {bundle.price_list.name}',
            )
            existing_items.add(pli.item_id)


@transaction.atomic
def post_delivery(delivery, user):
    """
    Post a Delivery Note: creates DELIVER StockMoves and updates balances.
    Before processing, ensures any SO bundle components are present as DN lines.
    """
    from sales.models import DeliveryNote, DeliveryLine
    from core.models import DocumentStatus

    if delivery.status != DocumentStatus.DRAFT:
        raise ValueError(f"Delivery {delivery.document_number} is not in DRAFT status.")

    # ── Expand missing SO bundle components into DN lines ──────────────
    _ensure_so_bundle_lines_on_delivery(delivery)

    now = timezone.now()
    moves = []
    skipped = []

    for line in delivery.lines.select_related('item__default_unit', 'item__selling_unit', 'unit').all():
        base_qty = _try_convert(line.qty, line.unit, line.item.stock_unit, line.item, line, skipped)
        if base_qty is None:
            continue
        move = StockMove(
            move_type=MoveType.DELIVER,
            item=line.item,
            qty=base_qty,
            unit=line.item.stock_unit,
            from_location=line.location,
            to_location=None,
            reference_type='DeliveryNote',
            reference_id=delivery.pk,
            reference_number=delivery.document_number,
            batch_number=getattr(line, 'batch_number', '') or '',
            serial_number=getattr(line, 'serial_number', '') or '',
            status=MoveStatus.POSTED,
            created_by=user,
            posted_by=user,
            posted_at=now,
        )
        moves.append(move)
        _update_balance(line.item, line.location, -base_qty)

        # Update SO delivered qty if linked (track in the SO line's own unit)
        if delivery.sales_order:
            so_lines = delivery.sales_order.lines.filter(item=line.item)
            for so_line in so_lines:
                so_line.qty_delivered += line.qty
                so_line.save(update_fields=['qty_delivered'])

    StockMove.objects.bulk_create(moves)

    delivery.status = DocumentStatus.POSTED
    delivery.posted_by = user
    delivery.posted_at = now
    delivery.save(update_fields=['status', 'posted_by', 'posted_at', 'updated_at'])

    _create_audit(user, 'POST', delivery, {'lines': len(moves), 'skipped_lines': len(skipped)})
    delivery.skipped_lines = skipped
    return delivery


@transaction.atomic
def post_sales_pickup(pickup, user):
    """
    Post a Sales Pickup: behaves like a Delivery Note but for PICKUP fulfillment.
    Creates DELIVER StockMoves and updates balances.
    Before processing, ensures any SO bundle components are present as Pickup lines.
    """
    from sales.models import SalesPickup, SalesPickupLine
    from core.models import DocumentStatus

    if pickup.status != DocumentStatus.DRAFT:
        raise ValueError(f"Pickup {pickup.document_number} is not in DRAFT status.")

    # ── Expand missing SO bundle components into Pickup lines ─────────
    _ensure_so_bundle_lines_on_pickup(pickup)

    now = timezone.now()
    moves = []
    skipped = []

    for line in pickup.lines.select_related('item__default_unit', 'item__selling_unit', 'unit').all():
        base_qty = _try_convert(line.qty, line.unit, line.item.stock_unit, line.item, line, skipped)
        if base_qty is None:
            continue
        move = StockMove(
            move_type=MoveType.DELIVER,
            item=line.item,
            qty=base_qty,
            unit=line.item.stock_unit,
            from_location=line.location,
            to_location=None,
            reference_type='SalesPickup',
            reference_id=pickup.pk,
            reference_number=pickup.document_number,
            batch_number=getattr(line, 'batch_number', '') or '',
            serial_number=getattr(line, 'serial_number', '') or '',
            status=MoveStatus.POSTED,
            created_by=user,
            posted_by=user,
            posted_at=now,
        )
        moves.append(move)
        _update_balance(line.item, line.location, -base_qty)

        # Update SO delivered qty if linked (track in the SO line's own unit)
        if pickup.sales_order:
            so_lines = pickup.sales_order.lines.filter(item=line.item)
            for so_line in so_lines:
                so_line.qty_delivered += line.qty
                so_line.save(update_fields=['qty_delivered'])

    StockMove.objects.bulk_create(moves)

    pickup.status = DocumentStatus.POSTED
    pickup.posted_by = user
    pickup.posted_at = now
    pickup.save(update_fields=['status', 'posted_by', 'posted_at', 'updated_at'])

    _create_audit(user, 'POST', pickup, {'lines': len(moves), 'skipped_lines': len(skipped)})
    pickup.skipped_lines = skipped
    return pickup


@transaction.atomic
def post_transfer(transfer, user):
    """
    Post a Stock Transfer: creates TRANSFER StockMoves (out + in) and updates balances.
    """
    from core.models import DocumentStatus

    if transfer.status != DocumentStatus.DRAFT:
        raise ValueError(f"Transfer {transfer.document_number} is not in DRAFT status.")

    now = timezone.now()
    moves = []
    skipped = []

    for line in transfer.lines.select_related('item__default_unit', 'item__selling_unit', 'unit').all():
        # Validate locations belong to correct warehouses
        if line.from_location.warehouse_id != transfer.from_warehouse_id:
            raise ValueError(
                f"From-location {line.from_location} does not belong to "
                f"warehouse {transfer.from_warehouse}."
            )
        if line.to_location.warehouse_id != transfer.to_warehouse_id:
            raise ValueError(
                f"To-location {line.to_location} does not belong to "
                f"warehouse {transfer.to_warehouse}."
            )
        base_qty = _try_convert(line.qty, line.unit, line.item.stock_unit, line.item, line, skipped)
        if base_qty is None:
            continue
        move = StockMove(
            move_type=MoveType.TRANSFER,
            item=line.item,
            qty=base_qty,
            unit=line.item.stock_unit,
            from_location=line.from_location,
            to_location=line.to_location,
            reference_type='StockTransfer',
            reference_id=transfer.pk,
            reference_number=transfer.document_number,
            batch_number=getattr(line, 'batch_number', '') or '',
            serial_number=getattr(line, 'serial_number', '') or '',
            status=MoveStatus.POSTED,
            created_by=user,
            posted_by=user,
            posted_at=now,
        )
        moves.append(move)
        _update_balance(line.item, line.from_location, -base_qty)
        _update_balance(line.item, line.to_location, base_qty)

    StockMove.objects.bulk_create(moves)

    transfer.status = DocumentStatus.POSTED
    transfer.posted_by = user
    transfer.posted_at = now
    transfer.save(update_fields=['status', 'posted_by', 'posted_at', 'updated_at'])

    _create_audit(user, 'POST', transfer, {'lines': len(moves), 'skipped_lines': len(skipped)})
    transfer.skipped_lines = skipped
    return transfer


@transaction.atomic
def post_adjustment(adjustment, user):
    """
    Post a Stock Adjustment: sets stock directly TO the new qty (qty_counted).
    Locks the balance row first, then overwrites qty_on_hand to the new value
    so the result is always exactly what was counted.
    """
    from core.models import DocumentStatus

    if adjustment.status not in (DocumentStatus.DRAFT, DocumentStatus.APPROVED):
        raise ValueError(f"Adjustment {adjustment.document_number} cannot be posted from {adjustment.status}.")

    now = timezone.now()
    moves = []
    skipped = []

    for line in adjustment.lines.select_related('item__default_unit', 'item__selling_unit', 'unit').all():
        # Convert the new counted qty to base/stock units
        new_qty = _try_convert(line.qty_counted, line.unit, line.item.stock_unit, line.item, line, skipped)
        if new_qty is None:
            continue

        # Lock the balance row and set it directly to the new qty
        balance, created = StockBalance.objects.select_for_update().get_or_create(
            item=line.item,
            location=line.location,
            defaults={'qty_on_hand': Decimal('0'), 'qty_reserved': Decimal('0')},
        )
        old_qty = balance.qty_on_hand
        base_diff = new_qty - old_qty

        if base_diff == 0:
            continue

        # Check negative stock
        warehouse = line.location.warehouse
        if not warehouse.allow_negative_stock and new_qty < 0:
            raise ValueError(
                f"Insufficient stock for {line.item.code} at {line.location}. "
                f"Cannot set balance to {new_qty}."
            )

        # Set balance directly to the new qty
        balance.qty_on_hand = new_qty
        balance.save()

        move = StockMove(
            move_type=MoveType.ADJUST,
            item=line.item,
            qty=abs(base_diff),
            unit=line.item.stock_unit,
            from_location=line.location if base_diff < 0 else None,
            to_location=line.location if base_diff > 0 else None,
            reference_type='StockAdjustment',
            reference_id=adjustment.pk,
            reference_number=adjustment.document_number,
            notes=f"Set to {line.qty_counted} {line.unit.abbreviation} (was {old_qty})",
            status=MoveStatus.POSTED,
            created_by=user,
            posted_by=user,
            posted_at=now,
        )
        moves.append(move)

    StockMove.objects.bulk_create(moves)

    adjustment.status = DocumentStatus.POSTED
    adjustment.posted_by = user
    adjustment.posted_at = now
    adjustment.save(update_fields=['status', 'posted_by', 'posted_at', 'updated_at'])

    _create_audit(user, 'POST', adjustment, {'lines': len(moves), 'skipped_lines': len(skipped)})
    adjustment.skipped_lines = skipped
    return adjustment


@transaction.atomic
def post_damaged_report(report, user):
    """
    Post a Damaged Report: creates DAMAGE StockMoves and decreases balances.
    """
    from core.models import DocumentStatus

    if report.status != DocumentStatus.DRAFT:
        raise ValueError(f"Damaged report {report.document_number} is not in DRAFT status.")

    now = timezone.now()
    moves = []
    skipped = []

    for line in report.lines.select_related('item__default_unit', 'item__selling_unit', 'unit').all():
        base_qty = _try_convert(line.qty, line.unit, line.item.stock_unit, line.item, line, skipped)
        if base_qty is None:
            continue
        move = StockMove(
            move_type=MoveType.DAMAGE,
            item=line.item,
            qty=base_qty,
            unit=line.item.stock_unit,
            from_location=line.location,
            to_location=None,
            reference_type='DamagedReport',
            reference_id=report.pk,
            reference_number=report.document_number,
            notes=line.reason,
            status=MoveStatus.POSTED,
            created_by=user,
            posted_by=user,
            posted_at=now,
        )
        moves.append(move)
        _update_balance(line.item, line.location, -base_qty)

    StockMove.objects.bulk_create(moves)

    report.status = DocumentStatus.POSTED
    report.posted_by = user
    report.posted_at = now
    report.save(update_fields=['status', 'posted_by', 'posted_at', 'updated_at'])

    _create_audit(user, 'POST', report, {'lines': len(moves), 'skipped_lines': len(skipped)})
    report.skipped_lines = skipped
    return report


@transaction.atomic
def reserve_stock(item, location, qty, reference_type, reference_id, user):
    """Reserve stock for a sales order or other purpose."""
    from inventory.models import StockReservation

    balance = StockBalance.objects.select_for_update().get(item=item, location=location)
    available = balance.qty_on_hand - balance.qty_reserved
    if qty > available:
        raise ValueError(
            f"Cannot reserve {qty} of {item.code} at {location}. Available: {available}"
        )

    balance.qty_reserved += qty
    balance.save(update_fields=['qty_reserved', 'updated_at'])

    reservation = StockReservation.objects.create(
        item=item,
        location=location,
        qty=qty,
        reference_type=reference_type,
        reference_id=reference_id,
        created_by=user,
    )

    _create_audit(user, 'RESERVE', reservation, {
        'item': item.code, 'qty': str(qty), 'location': str(location)
    })
    return reservation


@transaction.atomic
def cancel_document(doc, user):
    """
    Cancel a transactional document.
    - If DRAFT/APPROVED: simply mark CANCELLED.
    - If POSTED: create reversal StockMove rows and update balances, then mark CANCELLED.
    """
    from core.models import DocumentStatus

    if doc.status == DocumentStatus.CANCELLED:
        raise ValueError(f"{doc.document_number} is already cancelled.")

    now = timezone.now()

    if doc.status == DocumentStatus.POSTED:
        # Create reversal moves
        original_moves = StockMove.objects.filter(
            reference_type=doc.__class__.__name__,
            reference_id=doc.pk,
            status=MoveStatus.POSTED,
        )
        reversal_moves = []
        for orig in original_moves:
            reversal = StockMove(
                move_type=orig.move_type,
                item=orig.item,
                qty=orig.qty,
                unit=orig.unit,
                from_location=orig.to_location,
                to_location=orig.from_location,
                reference_type=orig.reference_type,
                reference_id=orig.reference_id,
                reference_number=f"REV-{orig.reference_number}",
                batch_number=orig.batch_number,
                serial_number=orig.serial_number,
                notes=f"Reversal of move #{orig.pk}",
                status=MoveStatus.POSTED,
                created_by=user,
                posted_by=user,
                posted_at=now,
            )
            reversal_moves.append(reversal)

            # Reverse balance effects
            if orig.to_location:
                _update_balance(orig.item, orig.to_location, -orig.qty)
            if orig.from_location:
                _update_balance(orig.item, orig.from_location, orig.qty)

        StockMove.objects.bulk_create(reversal_moves)

    doc.status = DocumentStatus.CANCELLED
    doc.save(update_fields=['status', 'updated_at'])
    _create_audit(user, 'CANCEL', doc, {'reversal_moves': doc.status == 'POSTED'})
    return doc


@transaction.atomic
def post_purchase_return(pr, user):
    """Post a Purchase Return: creates RETURN_OUT StockMoves and decreases balances."""
    from procurement.models import PurchaseReturn
    from core.models import DocumentStatus

    if pr.status != DocumentStatus.DRAFT:
        raise ValueError(f"Purchase Return {pr.document_number} is not in DRAFT status.")

    now = timezone.now()
    moves = []
    skipped = []

    for line in pr.lines.select_related('item__default_unit', 'item__selling_unit', 'unit').all():
        base_qty = _try_convert(line.qty, line.unit, line.item.stock_unit, line.item, line, skipped)
        if base_qty is None:
            continue
        move = StockMove(
            move_type=MoveType.RETURN_OUT,
            item=line.item,
            qty=base_qty,
            unit=line.item.stock_unit,
            from_location=line.location,
            to_location=None,
            reference_type='PurchaseReturn',
            reference_id=pr.pk,
            reference_number=pr.document_number,
            notes=line.reason,
            status=MoveStatus.POSTED,
            created_by=user,
            posted_by=user,
            posted_at=now,
        )
        moves.append(move)
        _update_balance(line.item, line.location, -base_qty)

    StockMove.objects.bulk_create(moves)

    pr.status = DocumentStatus.POSTED
    pr.posted_by = user
    pr.posted_at = now
    pr.save(update_fields=['status', 'posted_by', 'posted_at', 'updated_at'])

    _create_audit(user, 'POST', pr, {'lines': len(moves), 'skipped_lines': len(skipped)})
    pr.skipped_lines = skipped
    return pr


@transaction.atomic
def post_sales_return(sr, user):
    """Post a Sales Return: creates RETURN_IN StockMoves and increases balances."""
    from sales.models import SalesReturn
    from core.models import DocumentStatus

    if sr.status != DocumentStatus.DRAFT:
        raise ValueError(f"Sales Return {sr.document_number} is not in DRAFT status.")

    now = timezone.now()
    moves = []
    skipped = []

    for line in sr.lines.select_related('item__default_unit', 'item__selling_unit', 'unit').all():
        base_qty = _try_convert(line.qty, line.unit, line.item.stock_unit, line.item, line, skipped)
        if base_qty is None:
            continue
        move = StockMove(
            move_type=MoveType.RETURN_IN,
            item=line.item,
            qty=base_qty,
            unit=line.item.stock_unit,
            from_location=None,
            to_location=line.location,
            reference_type='SalesReturn',
            reference_id=sr.pk,
            reference_number=sr.document_number,
            notes=line.reason,
            status=MoveStatus.POSTED,
            created_by=user,
            posted_by=user,
            posted_at=now,
        )
        moves.append(move)
        _update_balance(line.item, line.location, base_qty)

    StockMove.objects.bulk_create(moves)

    sr.status = DocumentStatus.POSTED
    sr.posted_by = user
    sr.posted_at = now
    sr.save(update_fields=['status', 'posted_by', 'posted_at', 'updated_at'])

    _create_audit(user, 'POST', sr, {'lines': len(moves), 'skipped_lines': len(skipped)})
    sr.skipped_lines = skipped
    return sr


@transaction.atomic
def post_inventory_to_supply(ist, user):
    """
    Post an Inventory-to-Supply Transfer (IST).
    For each line:
      - Deduct StockBalance (inventory) for item @ location.
      - Create SUPPLY_OUT StockMove.
      - Auto-create or find matching SupplyItem based on catalog item.
      - Create SupplyMovement (IN) for the supply_item, using item.cost_price as unit cost.
    """
    from inventory.models import InventoryToSupplyTransfer
    from core.models import SupplyMovement, SupplyItem
    from core.models import DocumentStatus

    if ist.status != DocumentStatus.DRAFT:
        raise ValueError(f"IST {ist.document_number} is not in DRAFT status.")

    now = timezone.now()
    moves = []
    supply_movements = []
    skipped = []

    for line in ist.lines.select_related('item__default_unit', 'item__selling_unit', 'unit', 'location').all():
        base_qty = _try_convert(line.qty, line.unit, line.item.stock_unit, line.item, line, skipped)
        if base_qty is None:
            continue
        # Deduct inventory stock
        _update_balance(line.item, line.location, -base_qty)

        move = StockMove(
            move_type=MoveType.SUPPLY_OUT,
            item=line.item,
            qty=base_qty,
            unit=line.item.stock_unit,
            from_location=line.location,
            to_location=None,
            reference_type='InventoryToSupplyTransfer',
            reference_id=ist.pk,
            reference_number=ist.document_number,
            batch_number=line.batch_number or '',
            notes=line.notes or '',
            status=MoveStatus.POSTED,
            created_by=user,
            posted_by=user,
            posted_at=now,
        )
        moves.append(move)

        # Auto-create or find matching supply item based on catalog item
        # If supply_item was manually selected, use it; otherwise auto-create/find
        if hasattr(line, 'supply_item') and line.supply_item:
            supply_item = line.supply_item
        else:
            # Try to find existing supply item with matching code
            supply_item, created = SupplyItem.objects.get_or_create(
                code=line.item.code,
                defaults={
                    'name': line.item.name,
                    'unit': line.unit.abbreviation,
                    'cost_per_unit': line.item.cost_price or Decimal('0'),
                    'category': None,
                    'supplier_brand': '',
                    'notes': f'Auto-created from inventory item {line.item.code}',
                }
            )
            if created:
                _create_audit(user, 'AUTO_CREATE_SUPPLY', supply_item, {
                    'source': 'IST',
                    'catalog_item': line.item.code,
                })

        # Credit supply tracker
        unit_cost = (line.item.cost_price or Decimal('0'))
        sm = SupplyMovement(
            supply_item=supply_item,
            movement_type='IN',
            qty=line.qty,
            unit_cost=unit_cost,
            date=ist.transfer_date,
            batch_number=line.batch_number or '',
            reference=ist.document_number,
            notes=f"From inventory transfer {ist.document_number}",
            created_by=user,
        )
        supply_movements.append(sm)

    StockMove.objects.bulk_create(moves)

    # Save supply movements individually so the .save() triggers current_stock recalc
    for sm in supply_movements:
        sm.save()

    ist.status = DocumentStatus.POSTED
    ist.posted_by = user
    ist.posted_at = now
    ist.save(update_fields=['status', 'posted_by', 'posted_at', 'updated_at'])

    _create_audit(user, 'POST', ist, {'lines': len(moves), 'skipped_lines': len(skipped)})
    ist.skipped_lines = skipped
    return ist


@transaction.atomic
def cancel_inventory_to_supply(ist, user):
    """
    Cancel an Inventory-to-Supply Transfer.
    - DRAFT/APPROVED: mark cancelled (no moves to reverse).
    - POSTED: reverse StockMoves (restores inventory balance) AND
              create cancellation OUT SupplyMovements (restores supply tracker).
    """
    from core.models import DocumentStatus, SupplyMovement

    if ist.status == DocumentStatus.CANCELLED:
        raise ValueError(f"{ist.document_number} is already cancelled.")

    now = timezone.now()

    if ist.status == DocumentStatus.POSTED:
        # Reverse StockMoves (restores inventory StockBalance)
        original_moves = StockMove.objects.filter(
            reference_type='InventoryToSupplyTransfer',
            reference_id=ist.pk,
            status=MoveStatus.POSTED,
        )
        reversal_moves = []
        for orig in original_moves:
            reversal = StockMove(
                move_type=orig.move_type,
                item=orig.item,
                qty=orig.qty,
                unit=orig.unit,
                from_location=orig.to_location,
                to_location=orig.from_location,
                reference_type=orig.reference_type,
                reference_id=orig.reference_id,
                reference_number=f"REV-{orig.reference_number}",
                batch_number=orig.batch_number,
                notes=f"Reversal of move #{orig.pk}",
                status=MoveStatus.POSTED,
                created_by=user,
                posted_by=user,
                posted_at=now,
            )
            reversal_moves.append(reversal)
            if orig.from_location:
                _update_balance(orig.item, orig.from_location, orig.qty)

        StockMove.objects.bulk_create(reversal_moves)

        # Reverse SupplyMovements: add OUT movements to cancel each IN
        for line in ist.lines.select_related('supply_item', 'unit').all():
            sm_cancel = SupplyMovement(
                supply_item=line.supply_item,
                movement_type='OUT',
                qty=line.qty,
                unit_cost=Decimal('0'),
                date=timezone.now().date(),
                batch_number=line.batch_number or '',
                reference=f"CANCEL-{ist.document_number}",
                notes=f"Cancellation of {ist.document_number}",
                created_by=user,
            )
            sm_cancel.save()

    ist.status = DocumentStatus.CANCELLED
    ist.save(update_fields=['status', 'updated_at'])
    _create_audit(user, 'CANCEL', ist, {})
    return ist


def generate_document_number(prefix, model_class):
    """
    Generate sequential document numbers like PO-000001, GRN-000001, etc.

    Scans existing document_number values to find the highest numeric suffix
    matching the given prefix, then increments by 1. This is more reliable
    than using MAX(id) because IDs can have gaps from deletions.
    """
    import re

    pattern = re.compile(rf'^{re.escape(prefix)}-(\d+)$')
    max_num = 0
    # Use all_objects to include soft-deleted records
    for doc_num in model_class.all_objects.values_list('document_number', flat=True):
        if doc_num:
            m = pattern.match(doc_num)
            if m:
                num = int(m.group(1))
                if num > max_num:
                    max_num = num
    return f"{prefix}-{max_num + 1:06d}"


def save_with_document_number(instance, prefix, model_class, max_retries=5):
    """
    Save a TransactionalDocument instance with automatic document number
    generation and retry logic for handling unique constraint violations.

    Always regenerates the document number at save time to avoid stale
    numbers from form pre-fill. Retries up to max_retries times on collision.

    Uses savepoints so that a failed INSERT doesn't abort the outer transaction.

    Returns the saved instance.
    """
    from django.db import IntegrityError, transaction

    for attempt in range(max_retries):
        instance.document_number = generate_document_number(prefix, model_class)
        try:
            with transaction.atomic():
                instance.save()
            return instance
        except IntegrityError as e:
            if 'document_number' in str(e) and attempt < max_retries - 1:
                instance.pk = None  # Reset PK so Django treats it as a new insert
                continue
            else:
                raise
    return instance
