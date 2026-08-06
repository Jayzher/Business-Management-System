"""
POS posting engine — checkout, refund, void, shift management.
All stock changes delegate to inventory.services._update_balance for consistency.
"""
from decimal import Decimal
from django.db import transaction
from django.utils import timezone

from inventory.models import StockMove, StockBalance, MoveType, MoveStatus
from inventory.services import _update_balance, _create_audit, _sync_moves
from catalog.models import convert_to_base_unit
from pos.models import (
    POSSale, POSSaleLine, POSSaleBundleLine, POSPayment,
    POSRefund, POSRefundLine,
    POSShift, ShiftStatus, SaleStatus, RefundStatus,
    PaymentMethod, CashEntry, CashEntryType,
)


def generate_sale_number():
    """Generate sequential POS sale number like POS-000001."""
    last = POSSale.objects.order_by('-id').first()
    next_num = (last.id + 1) if last else 1
    return f"POS-{next_num:06d}"


def generate_refund_number():
    """Generate sequential POS refund number like RFN-000001."""
    last = POSRefund.objects.order_by('-id').first()
    next_num = (last.id + 1) if last else 1
    return f"RFN-{next_num:06d}"


@transaction.atomic
def open_shift(register, user, opening_cash=Decimal('0')):
    """Open a new cash shift for a register."""
    # Check no other OPEN shift on this register
    if POSShift.objects.filter(register=register, status=ShiftStatus.OPEN).exists():
        raise ValueError(f"Register '{register.name}' already has an open shift.")

    shift = POSShift.objects.create(
        register=register,
        opened_by=user,
        opened_at=timezone.now(),
        opening_cash=opening_cash,
        status=ShiftStatus.OPEN,
    )
    _create_audit(user, 'CREATE', shift, {'action': 'open_shift', 'opening_cash': str(opening_cash)})
    return shift


@transaction.atomic
def close_shift(shift, user, closing_cash_declared=Decimal('0')):
    """Close an open shift, computing variance."""
    if shift.status != ShiftStatus.OPEN:
        raise ValueError("Shift is not open.")

    now = timezone.now()

    # Recompute totals from actual sale/refund/cash-entry records.
    # PARTIALLY_REFUNDED sales still had their original payment land in the
    # drawer (only part of it was later handed back — that part is already
    # subtracted below via cash_refund_total), so they must stay counted
    # here the same as PAID/POSTED.
    from django.db.models import Sum, Q
    _payable_statuses = [SaleStatus.PAID, SaleStatus.POSTED, SaleStatus.PARTIALLY_REFUNDED]
    cash_sales = POSPayment.objects.filter(
        sale__shift=shift,
        sale__status__in=_payable_statuses,
        method=PaymentMethod.CASH,
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0')

    noncash_sales = POSPayment.objects.filter(
        sale__shift=shift,
        sale__status__in=_payable_statuses,
    ).exclude(method=PaymentMethod.CASH).aggregate(total=Sum('amount'))['total'] or Decimal('0')

    refund_total = POSRefund.objects.filter(
        shift=shift,
        status=RefundStatus.POSTED,
    ).aggregate(total=Sum('grand_total'))['total'] or Decimal('0')

    # Only cash-method refunds actually leave the drawer — a refund given
    # back via GCash/card/bank transfer shouldn't reduce expected cash.
    cash_refund_total = POSRefund.objects.filter(
        shift=shift,
        status=RefundStatus.POSTED,
        method=PaymentMethod.CASH,
    ).aggregate(total=Sum('grand_total'))['total'] or Decimal('0')

    cash_in = CashEntry.objects.filter(
        shift=shift, entry_type=CashEntryType.CASH_IN,
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
    cash_out = CashEntry.objects.filter(
        shift=shift, entry_type=CashEntryType.CASH_OUT,
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0')

    shift.cash_sales_total = cash_sales
    shift.noncash_sales_total = noncash_sales
    shift.refund_total = refund_total
    shift.cash_refund_total = cash_refund_total
    shift.cash_in_out_total = cash_in - cash_out
    shift.closing_cash_declared = closing_cash_declared
    shift.closed_by = user
    shift.closed_at = now
    shift.status = ShiftStatus.CLOSED
    shift.save()

    _create_audit(user, 'UPDATE', shift, {
        'action': 'close_shift',
        'expected_cash': str(shift.expected_cash),
        'declared': str(closing_cash_declared),
        'variance': str(shift.variance),
    })
    return shift


@transaction.atomic
def post_pos_sale(sale_id, user):
    """
    Post a POS sale: validate payments, create StockMove rows, update balances.
    Sale must be in PAID status with shift OPEN.
    """
    sale = POSSale.objects.select_for_update().get(pk=sale_id)

    if sale.status != SaleStatus.PAID:
        raise ValueError(f"Sale {sale.sale_no} is not in PAID status (current: {sale.status}).")

    shift = sale.shift
    if shift.status != ShiftStatus.OPEN:
        raise ValueError(f"Shift #{shift.pk} is not open. Cannot post sale.")

    # Validate payments sum
    payment_sum = sum(p.amount for p in sale.payments.all())
    if payment_sum < sale.grand_total:
        raise ValueError(
            f"Payment total ({payment_sum}) is less than grand total ({sale.grand_total})."
        )

    now = timezone.now()
    moves = []
    skipped = []
    warehouse = sale.warehouse

    for line in sale.lines.select_related('item__default_unit', 'item__selling_unit', 'unit', 'location').all():
        loc = line.location or sale.location
        try:
            base_qty = convert_to_base_unit(line.qty, line.unit, line.item.stock_unit, item=line.item)
        except (ValueError, Exception):
            skipped.append(
                f"{line.item.code} ({line.qty} {line.unit.abbreviation} → {line.item.stock_unit.abbreviation})"
            )
            continue

        # Stock availability check (with row locking)
        balance, _ = StockBalance.objects.select_for_update().get_or_create(
            item=line.item, location=loc,
            defaults={'qty_on_hand': Decimal('0'), 'qty_reserved': Decimal('0')},
        )
        available = balance.qty_on_hand - balance.qty_reserved
        if base_qty > available and not warehouse.allow_negative_stock:
            raise ValueError(
                f"Insufficient stock for {line.item.code} at {loc}. "
                f"Available: {available}, Requested: {base_qty} {line.item.stock_unit.abbreviation}"
            )

        move = StockMove(
            move_type=MoveType.POS_SALE,
            item=line.item,
            qty=base_qty,
            unit=line.item.stock_unit,
            from_location=loc,
            to_location=None,
            reference_type='POSSale',
            reference_id=sale.pk,
            reference_number=sale.sale_no,
            batch_number=line.batch_number,
            serial_number=line.serial_number,
            status=MoveStatus.POSTED,
            created_by=user,
            posted_by=user,
            posted_at=now,
        )
        moves.append(move)

        # Update balance
        balance.qty_on_hand -= base_qty
        balance.save()

    # Expand bundle lines into per-item stock moves
    for bundle_line in sale.bundle_lines.select_related('price_list').prefetch_related(
        'price_list__items__item__stock_unit', 'price_list__items__unit',
    ).all():
        for pli in bundle_line.price_list.items.all():
            item = pli.item
            qty = pli.min_qty * bundle_line.qty_sets
            if qty <= 0:
                continue
            try:
                base_qty = convert_to_base_unit(qty, pli.unit, item.stock_unit, item=item)
            except (ValueError, Exception):
                skipped.append(
                    f"{item.code} ({qty} {pli.unit.abbreviation} → {item.stock_unit.abbreviation})"
                )
                continue

            loc = sale.location
            balance, _ = StockBalance.objects.select_for_update().get_or_create(
                item=item, location=loc,
                defaults={'qty_on_hand': Decimal('0'), 'qty_reserved': Decimal('0')},
            )
            available = balance.qty_on_hand - balance.qty_reserved
            if base_qty > available and not warehouse.allow_negative_stock:
                raise ValueError(
                    f"[Bundle: {bundle_line.price_list.name}] Insufficient stock for {item.code} at {loc}. "
                    f"Available: {available}, Requested: {base_qty} {item.stock_unit.abbreviation}"
                )

            move = StockMove(
                move_type=MoveType.POS_SALE,
                item=item,
                qty=base_qty,
                unit=item.stock_unit,
                from_location=loc,
                to_location=None,
                reference_type='POSSale',
                reference_id=sale.pk,
                reference_number=sale.sale_no,
                batch_number='',
                serial_number='',
                status=MoveStatus.POSTED,
                created_by=user,
                posted_by=user,
                posted_at=now,
            )
            moves.append(move)
            balance.qty_on_hand -= base_qty
            balance.save()

    StockMove.objects.bulk_create(moves)
    _sync_moves(moves)

    sale.status = SaleStatus.POSTED
    sale.posted_by = user
    sale.posted_at = now
    sale.stock_deducted = True
    sale.save(update_fields=['status', 'posted_by', 'posted_at', 'stock_deducted', 'updated_at'])

    # Update shift totals
    _update_shift_totals(shift)

    # Auto-create Invoice
    from inventory.automation import auto_create_invoice_from_pos_sale
    auto_create_invoice_from_pos_sale(sale, user)

    sale.skipped_lines = skipped

    _create_audit(user, 'POST', sale, {'lines': len(moves), 'grand_total': str(sale.grand_total)})
    return sale


@transaction.atomic
def sync_pos_sale_stock_moves(sale_id, user):
    """Idempotent backfill: ensure StockMove rows exist for a completed POS sale.

    If no StockMove rows exist for this sale, create them and deduct balances.
    Then mark sale.stock_deducted=True.
    """
    sale = POSSale.objects.select_for_update().select_related('warehouse', 'location').get(pk=sale_id)

    if sale.status not in [SaleStatus.PAID, SaleStatus.POSTED]:
        return sale

    # If we already marked deducted, skip.
    if sale.stock_deducted:
        return sale

    existing = StockMove.objects.filter(
        reference_type='POSSale', reference_id=sale.pk, status=MoveStatus.POSTED,
    )
    if existing.exists():
        sale.stock_deducted = True
        sale.save(update_fields=['stock_deducted', 'updated_at'])
        return sale

    now = timezone.now()
    moves = []
    skipped_deduct = []
    warehouse = sale.warehouse

    for line in sale.lines.select_related('item__default_unit', 'item__selling_unit', 'unit', 'location').all():
        loc = line.location or sale.location
        try:
            base_qty = convert_to_base_unit(line.qty, line.unit, line.item.stock_unit, item=line.item)
        except (ValueError, Exception):
            skipped_deduct.append(
                f"{line.item.code} ({line.qty} {line.unit.abbreviation} → {line.item.stock_unit.abbreviation})"
            )
            continue

        # Deduct using the core inventory helper (enforces negative-stock rule)
        _update_balance(line.item, loc, -base_qty)

        moves.append(StockMove(
            move_type=MoveType.POS_SALE,
            item=line.item,
            qty=base_qty,
            unit=line.item.stock_unit,
            from_location=loc,
            to_location=None,
            reference_type='POSSale',
            reference_id=sale.pk,
            reference_number=sale.sale_no,
            batch_number=line.batch_number,
            serial_number=line.serial_number,
            status=MoveStatus.POSTED,
            created_by=user,
            posted_by=user,
            posted_at=now,
            notes='Backfilled stock move from POS receipt sync',
        ))

    StockMove.objects.bulk_create(moves)
    _sync_moves(moves)
    sale.stock_deducted = True
    # If the sale was PAID but not POSTED, we keep the status as-is (this is sync only).
    sale.save(update_fields=['stock_deducted', 'updated_at'])
    _create_audit(user, 'SYNC', sale, {'action': 'sync_pos_sale_stock_moves', 'lines': len(moves)})
    sale.skipped_lines = skipped_deduct
    return sale


@transaction.atomic
def post_pos_refund(refund_id, user):
    """
    Post a POS refund: create RETURN_IN StockMove rows, update balances and shift.
    """
    refund = POSRefund.objects.select_for_update().get(pk=refund_id)

    if refund.status != RefundStatus.DRAFT:
        raise ValueError(f"Refund {refund.refund_no} is not in DRAFT status.")

    shift = refund.shift
    if shift.status != ShiftStatus.OPEN:
        raise ValueError("Shift is not open. Cannot post refund.")

    now = timezone.now()
    moves = []
    skipped_refund = []

    for line in refund.lines.select_related('item__default_unit', 'item__selling_unit', 'unit', 'location').all():
        try:
            base_qty = convert_to_base_unit(line.qty, line.unit, line.item.stock_unit, item=line.item)
        except (ValueError, Exception):
            skipped_refund.append(
                f"{line.item.code} ({line.qty} {line.unit.abbreviation} → {line.item.stock_unit.abbreviation})"
            )
            continue
        move = StockMove(
            move_type=MoveType.RETURN_IN,
            item=line.item,
            qty=base_qty,
            unit=line.item.stock_unit,
            from_location=None,
            to_location=line.location,
            reference_type='POSRefund',
            reference_id=refund.pk,
            reference_number=refund.refund_no,
            status=MoveStatus.POSTED,
            created_by=user,
            posted_by=user,
            posted_at=now,
        )
        moves.append(move)
        _update_balance(line.item, line.location, base_qty)

    StockMove.objects.bulk_create(moves)
    _sync_moves(moves)

    refund.status = RefundStatus.POSTED
    refund.posted_by = user
    refund.posted_at = now
    refund.save(update_fields=['status', 'posted_by', 'posted_at', 'updated_at'])

    # Mark original sale as fully or partially refunded, depending on
    # whether every line has now been refunded in full — a refund covering
    # only some lines/qty must not make the whole sale disappear from
    # revenue reports (see SaleStatus.PARTIALLY_REFUNDED).
    original = refund.original_sale
    fully_refunded = all(
        line.qty_refundable <= 0 for line in original.lines.all()
    )
    original.status = SaleStatus.REFUNDED if fully_refunded else SaleStatus.PARTIALLY_REFUNDED
    original.save(update_fields=['status', 'updated_at'])

    _update_shift_totals(shift)
    _create_audit(user, 'POST', refund, {'lines': len(moves), 'grand_total': str(refund.grand_total)})
    refund.skipped_lines = skipped_refund
    return refund


@transaction.atomic
def void_sale(sale_id, user):
    """
    Void a POS sale.
    - If DRAFT/PAID (not posted): simply mark VOID.
    - If POSTED: create reversal StockMove rows, then mark VOID.
    """
    sale = POSSale.objects.select_for_update().get(pk=sale_id)

    if sale.status == SaleStatus.VOID:
        raise ValueError(f"Sale {sale.sale_no} is already void.")
    if sale.status in (SaleStatus.REFUNDED, SaleStatus.PARTIALLY_REFUNDED):
        raise ValueError(f"Sale {sale.sale_no} has already been refunded, cannot void.")

    now = timezone.now()

    if sale.status == SaleStatus.POSTED:
        # Create reversal moves
        original_moves = StockMove.objects.filter(
            reference_type='POSSale',
            reference_id=sale.pk,
            status=MoveStatus.POSTED,
        )
        reversal_moves = []
        for orig in original_moves:
            reversal = StockMove(
                move_type=MoveType.RETURN_IN,
                item=orig.item,
                qty=orig.qty,
                unit=orig.unit,
                from_location=None,
                to_location=orig.from_location,
                reference_type='POSSale',
                reference_id=sale.pk,
                reference_number=f"VOID-{sale.sale_no}",
                notes=f"Void reversal of {sale.sale_no}",
                status=MoveStatus.POSTED,
                created_by=user,
                posted_by=user,
                posted_at=now,
            )
            reversal_moves.append(reversal)
            if orig.from_location:
                _update_balance(orig.item, orig.from_location, orig.qty)

        StockMove.objects.bulk_create(reversal_moves)
        _sync_moves(reversal_moves)

    sale.status = SaleStatus.VOID
    sale.save(update_fields=['status', 'updated_at'])

    if sale.shift.status == ShiftStatus.OPEN:
        _update_shift_totals(sale.shift)

    _create_audit(user, 'CANCEL', sale, {'action': 'void_sale'})
    return sale


def _update_shift_totals(shift):
    """Recompute shift stored totals from actual records."""
    from django.db.models import Sum

    # See close_shift() above for why PARTIALLY_REFUNDED must stay counted.
    _payable_statuses = [SaleStatus.PAID, SaleStatus.POSTED, SaleStatus.PARTIALLY_REFUNDED]
    cash_sales = POSPayment.objects.filter(
        sale__shift=shift,
        sale__status__in=_payable_statuses,
        method=PaymentMethod.CASH,
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0')

    noncash_sales = POSPayment.objects.filter(
        sale__shift=shift,
        sale__status__in=_payable_statuses,
    ).exclude(method=PaymentMethod.CASH).aggregate(total=Sum('amount'))['total'] or Decimal('0')

    refund_total = POSRefund.objects.filter(
        shift=shift, status=RefundStatus.POSTED,
    ).aggregate(total=Sum('grand_total'))['total'] or Decimal('0')

    # Only cash-method refunds actually leave the drawer.
    cash_refund_total = POSRefund.objects.filter(
        shift=shift, status=RefundStatus.POSTED, method=PaymentMethod.CASH,
    ).aggregate(total=Sum('grand_total'))['total'] or Decimal('0')

    cash_in = CashEntry.objects.filter(
        shift=shift, entry_type=CashEntryType.CASH_IN,
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
    cash_out = CashEntry.objects.filter(
        shift=shift, entry_type=CashEntryType.CASH_OUT,
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0')

    shift.cash_sales_total = cash_sales
    shift.noncash_sales_total = noncash_sales
    shift.refund_total = refund_total
    shift.cash_refund_total = cash_refund_total
    shift.cash_in_out_total = cash_in - cash_out
    shift.save(update_fields=[
        'cash_sales_total', 'noncash_sales_total',
        'refund_total', 'cash_refund_total', 'cash_in_out_total', 'updated_at',
    ])
