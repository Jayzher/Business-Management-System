"""
Inventory posting engine — the core business logic.
All stock changes go through this service to ensure consistency.
"""
from decimal import Decimal
from django.db import transaction
from django.utils import timezone

from inventory.models import (
    StockMove, StockBalance, MoveType, MoveStatus,
    StockTransfer, StockAdjustment, DamagedReport,
)
from audit.models import AuditLog


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
    """Create an audit log entry."""
    AuditLog.objects.create(
        user=user,
        action=action,
        model_name=obj.__class__.__name__,
        object_id=obj.pk,
        object_repr=str(obj)[:255],
        changes=changes or {},
    )


@transaction.atomic
def post_goods_receipt(grn, user):
    """
    Post a GRN: creates RECEIVE StockMoves and updates balances.
    """
    from procurement.models import GoodsReceipt
    from core.models import DocumentStatus

    if grn.status != DocumentStatus.DRAFT:
        raise ValueError(f"GRN {grn.document_number} is not in DRAFT status.")

    now = timezone.now()
    moves = []

    for line in grn.lines.all():
        move = StockMove(
            move_type=MoveType.RECEIVE,
            item=line.item,
            qty=line.qty,
            unit=line.unit,
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
        _update_balance(line.item, line.location, line.qty)

        # Update PO received qty if linked
        if grn.purchase_order:
            po_lines = grn.purchase_order.lines.filter(item=line.item)
            for po_line in po_lines:
                po_line.qty_received += line.qty
                po_line.save(update_fields=['qty_received'])

    StockMove.objects.bulk_create(moves)

    # Weighted average cost update
    from catalog.models import Item
    for line in grn.lines.select_related('item').all():
        item = line.item
        if item.cost_price is None:
            item.cost_price = Decimal('0')
        total_existing_qty = sum(
            b.qty_on_hand for b in StockBalance.objects.filter(item=item)
        )
        # total_existing_qty already includes the qty we just added
        old_qty = total_existing_qty - line.qty
        if old_qty + line.qty > 0:
            po_unit_price = Decimal('0')
            if grn.purchase_order:
                po_line = grn.purchase_order.lines.filter(item=line.item).first()
                if po_line:
                    po_unit_price = po_line.unit_price
            if po_unit_price > 0:
                old_value = old_qty * item.cost_price
                new_value = line.qty * po_unit_price
                item.cost_price = (old_value + new_value) / (old_qty + line.qty)
                item.save(update_fields=['cost_price', 'updated_at'])

    grn.status = DocumentStatus.POSTED
    grn.posted_by = user
    grn.posted_at = now
    grn.save(update_fields=['status', 'posted_by', 'posted_at', 'updated_at'])

    _create_audit(user, 'POST', grn, {'lines': len(moves)})
    return grn


@transaction.atomic
def post_delivery(delivery, user):
    """
    Post a Delivery Note: creates DELIVER StockMoves and updates balances.
    """
    from sales.models import DeliveryNote
    from core.models import DocumentStatus

    if delivery.status != DocumentStatus.DRAFT:
        raise ValueError(f"Delivery {delivery.document_number} is not in DRAFT status.")

    now = timezone.now()
    moves = []

    for line in delivery.lines.all():
        move = StockMove(
            move_type=MoveType.DELIVER,
            item=line.item,
            qty=line.qty,
            unit=line.unit,
            from_location=line.location,
            to_location=None,
            reference_type='DeliveryNote',
            reference_id=delivery.pk,
            reference_number=delivery.document_number,
            status=MoveStatus.POSTED,
            created_by=user,
            posted_by=user,
            posted_at=now,
        )
        moves.append(move)
        _update_balance(line.item, line.location, -line.qty)

        # Update SO delivered qty if linked
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

    _create_audit(user, 'POST', delivery, {'lines': len(moves)})
    return delivery


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

    for line in transfer.lines.all():
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
        move = StockMove(
            move_type=MoveType.TRANSFER,
            item=line.item,
            qty=line.qty,
            unit=line.unit,
            from_location=line.from_location,
            to_location=line.to_location,
            reference_type='StockTransfer',
            reference_id=transfer.pk,
            reference_number=transfer.document_number,
            status=MoveStatus.POSTED,
            created_by=user,
            posted_by=user,
            posted_at=now,
        )
        moves.append(move)
        _update_balance(line.item, line.from_location, -line.qty)
        _update_balance(line.item, line.to_location, line.qty)

    StockMove.objects.bulk_create(moves)

    transfer.status = DocumentStatus.POSTED
    transfer.posted_by = user
    transfer.posted_at = now
    transfer.save(update_fields=['status', 'posted_by', 'posted_at', 'updated_at'])

    _create_audit(user, 'POST', transfer, {'lines': len(moves)})
    return transfer


@transaction.atomic
def post_adjustment(adjustment, user):
    """
    Post a Stock Adjustment: creates ADJUST StockMoves for differences.
    """
    from core.models import DocumentStatus

    if adjustment.status not in (DocumentStatus.DRAFT, DocumentStatus.APPROVED):
        raise ValueError(f"Adjustment {adjustment.document_number} cannot be posted from {adjustment.status}.")

    now = timezone.now()
    moves = []

    for line in adjustment.lines.all():
        diff = line.qty_counted - line.qty_system
        if diff == 0:
            continue

        move = StockMove(
            move_type=MoveType.ADJUST,
            item=line.item,
            qty=abs(diff),
            unit=line.unit,
            from_location=line.location if diff < 0 else None,
            to_location=line.location if diff > 0 else None,
            reference_type='StockAdjustment',
            reference_id=adjustment.pk,
            reference_number=adjustment.document_number,
            notes=f"Adjustment: system={line.qty_system}, counted={line.qty_counted}",
            status=MoveStatus.POSTED,
            created_by=user,
            posted_by=user,
            posted_at=now,
        )
        moves.append(move)
        _update_balance(line.item, line.location, diff)

    StockMove.objects.bulk_create(moves)

    adjustment.status = DocumentStatus.POSTED
    adjustment.posted_by = user
    adjustment.posted_at = now
    adjustment.save(update_fields=['status', 'posted_by', 'posted_at', 'updated_at'])

    _create_audit(user, 'POST', adjustment, {'lines': len(moves)})
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

    for line in report.lines.all():
        move = StockMove(
            move_type=MoveType.DAMAGE,
            item=line.item,
            qty=line.qty,
            unit=line.unit,
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
        _update_balance(line.item, line.location, -line.qty)

    StockMove.objects.bulk_create(moves)

    report.status = DocumentStatus.POSTED
    report.posted_by = user
    report.posted_at = now
    report.save(update_fields=['status', 'posted_by', 'posted_at', 'updated_at'])

    _create_audit(user, 'POST', report, {'lines': len(moves)})
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

    for line in pr.lines.all():
        move = StockMove(
            move_type=MoveType.RETURN_OUT,
            item=line.item,
            qty=line.qty,
            unit=line.unit,
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
        _update_balance(line.item, line.location, -line.qty)

    StockMove.objects.bulk_create(moves)

    pr.status = DocumentStatus.POSTED
    pr.posted_by = user
    pr.posted_at = now
    pr.save(update_fields=['status', 'posted_by', 'posted_at', 'updated_at'])

    _create_audit(user, 'POST', pr, {'lines': len(moves)})
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

    for line in sr.lines.all():
        move = StockMove(
            move_type=MoveType.RETURN_IN,
            item=line.item,
            qty=line.qty,
            unit=line.unit,
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
        _update_balance(line.item, line.location, line.qty)

    StockMove.objects.bulk_create(moves)

    sr.status = DocumentStatus.POSTED
    sr.posted_by = user
    sr.posted_at = now
    sr.save(update_fields=['status', 'posted_by', 'posted_at', 'updated_at'])

    _create_audit(user, 'POST', sr, {'lines': len(moves)})
    return sr


def generate_document_number(prefix, model_class):
    """Generate sequential document numbers like PO-000001, GRN-000001, etc."""
    last = model_class.all_objects.order_by('-id').first()
    next_num = (last.id + 1) if last else 1
    return f"{prefix}-{next_num:06d}"
