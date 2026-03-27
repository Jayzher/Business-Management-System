"""
Cashflow auto-generation signals.

Real-time per-document signals handle procurement and expenses only.
Sales revenue (DeliveryNote, SalesPickup, POSSale, SalesReturn) is NOT
created here -- use the weekly sync (cashflow.sync.sync_weekly_sales_revenue)
which aggregates Revenue - COGS into a single CASH_IN/SALES entry per ISO week.

Covered here:
  CASH_OUT:
    * GoodsReceipt   POSTED -> CASH_OUT / PROCUREMENT
    * Expense        PAID   -> CASH_OUT / EXPENSES

  CASH_IN:
    * PurchaseReturn POSTED -> CASH_IN  / PROCUREMENT  (supplier refund)
"""

from decimal import Decimal

from django.db.models.signals import post_save
from django.dispatch import receiver


def _already_exists(source_type, source_id):
    from cashflow.models import CashFlowTransaction
    return CashFlowTransaction.objects.filter(
        source_type=source_type, source_id=source_id,
    ).exists()


def _create_auto_entry(
    *,
    source_type,
    source_id,
    source_number,
    flow_type,
    category,
    amount,
    transaction_date,
    reason,
    reference_no,
    user,
    payment_method=None,
    notes='',
):
    """Create one auto-generated CashFlowTransaction + audit log entry."""
    if amount <= 0:
        return None
    if _already_exists(source_type, source_id):
        return None

    from cashflow.models import (
        CashFlowTransaction, CashFlowType, CashFlowStatus,
        PaymentMethod, CashFlowLog, CashFlowLogAction,
    )

    pm = payment_method or PaymentMethod.CASH

    txn = CashFlowTransaction.objects.create(
        transaction_number=CashFlowTransaction.generate_next_number(),
        category=category,
        flow_type=flow_type,
        amount=amount,
        transaction_date=transaction_date,
        payment_method=pm,
        reference_no=reference_no or source_number,
        reason=reason,
        notes=notes,
        status=CashFlowStatus.PENDING,
        created_by=user,
        source_type=source_type,
        source_id=source_id,
        is_auto_generated=True,
    )

    CashFlowLog.objects.create(
        transaction=txn,
        action=CashFlowLogAction.CREATED,
        performed_by=user,
        details=f'Auto-generated from {source_type} {source_number}.',
    )
    return txn


def _is_newly_posted(instance, kwargs):
    """Return True only when this save() moved the instance to POSTED."""
    from core.models import DocumentStatus
    if instance.status != DocumentStatus.POSTED:
        return False
    update_fields = kwargs.get('update_fields')
    if update_fields is not None:
        return 'status' in update_fields
    return True


# ── GoodsReceipt → CASH_OUT / PROCUREMENT ────────────────────────────────

@receiver(post_save, sender='procurement.GoodsReceipt')
def grn_posted_to_cashflow(sender, instance, created, **kwargs):
    """GRN posted: record expected cash-out for the procurement cost."""
    if not _is_newly_posted(instance, kwargs):
        return
    if _already_exists('GoodsReceipt', instance.pk):
        return

    total = Decimal('0')
    for line in instance.lines.select_related('item', 'unit').all():
        unit_price = Decimal('0')
        if instance.purchase_order:
            po_line = (
                instance.purchase_order.lines
                .filter(item=line.item)
                .only('unit_price')
                .first()
            )
            if po_line:
                unit_price = po_line.unit_price
        if unit_price == 0:
            unit_price = getattr(line.item, 'cost_price', None) or Decimal('0')
        total += line.qty * unit_price

    user = instance.posted_by or instance.created_by
    supplier_name = instance.supplier.name if instance.supplier_id else 'Unknown supplier'

    _create_auto_entry(
        source_type='GoodsReceipt',
        source_id=instance.pk,
        source_number=instance.document_number,
        flow_type='CASH_OUT',
        category='PROCUREMENT',
        amount=total,
        transaction_date=instance.receipt_date,
        reason=f'Goods received: {instance.document_number} from {supplier_name}',
        reference_no=instance.document_number,
        user=user,
    )


# ── PurchaseReturn → CASH_IN / PROCUREMENT (supplier refund) ─────────────

@receiver(post_save, sender='procurement.PurchaseReturn')
def purchase_return_posted_to_cashflow(sender, instance, created, **kwargs):
    """Purchase Return posted: record expected cash-in refund from supplier."""
    if not _is_newly_posted(instance, kwargs):
        return
    if _already_exists('PurchaseReturn', instance.pk):
        return

    total = Decimal('0')
    for line in instance.lines.select_related('item').all():
        unit_price = Decimal('0')
        # 1. Use the original PO unit price via the linked GRN
        if instance.goods_receipt_id:
            grn = instance.goods_receipt
            if grn.purchase_order_id:
                po_line = (
                    grn.purchase_order.lines
                    .filter(item=line.item)
                    .only('unit_price')
                    .first()
                )
                if po_line:
                    unit_price = po_line.unit_price
        # 2. Fall back to item cost price
        if not unit_price:
            unit_price = getattr(line.item, 'cost_price', None) or Decimal('0')
        total += line.qty * unit_price

    user = instance.posted_by or instance.created_by
    supplier_name = instance.supplier.name if instance.supplier_id else 'Unknown supplier'

    _create_auto_entry(
        source_type='PurchaseReturn',
        source_id=instance.pk,
        source_number=instance.document_number,
        flow_type='CASH_IN',
        category='PROCUREMENT',
        amount=total,
        transaction_date=instance.return_date,
        reason=f'Purchase return: {instance.document_number} to {supplier_name}',
        reference_no=instance.document_number,
        user=user,
    )


# ── Expense → CASH_OUT / EXPENSES ────────────────────────────────────────

@receiver(post_save, sender='core.Expense')
def expense_paid_to_cashflow(sender, instance, created, **kwargs):
    """Expense saved as PAID: record cash-out."""
    from core.models import ExpenseStatus
    if instance.status != ExpenseStatus.PAID:
        return
    if _already_exists('Expense', instance.pk):
        return

    _create_auto_entry(
        source_type='Expense',
        source_id=instance.pk,
        source_number=str(instance.pk),
        flow_type='CASH_OUT',
        category='EXPENSES',
        amount=instance.amount,
        transaction_date=instance.date,
        reason=(
            f'{instance.category.name}: {instance.item_description}'
            if instance.item_description
            else instance.category.name
        ),
        reference_no=instance.reference_no or '',
        notes=instance.memo or '',
        user=instance.created_by,
    )
