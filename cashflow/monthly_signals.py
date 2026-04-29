"""
Monthly Cashflow Signals
=========================
Automatically update monthly cashflow summaries when transactions occur.

This module uses the same calculation logic as the management command
(calculate_monthly_cashflow) to ensure consistency between real-time
signal updates and batch recalculations.

Key accounting principles:
  - Cash Flow: Cash basis (when money moves)
  - P&L: Accrual basis (when revenue is earned / expenses incurred)
  - Balance Sheet: Total Assets = Cash + Inventory + AR
"""
from datetime import date, datetime, time
from decimal import Decimal

from django.db.models import Sum
from django.db.models.functions import Coalesce
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.utils import timezone

from cashflow.models import (
    MonthlyCashflowSummary, CashFlowTransaction,
    CashFlowType, CashFlowStatus, CashFlowCategory,
)
from core.models import Expense, Invoice, InvoicePayment, DocumentStatus
from pos.models import POSSale, SaleStatus
from sales.models import DeliveryNote, SalesPickup
from procurement.models import GoodsReceipt
from inventory.models import StockMove, MoveType, MoveStatus
from catalog.models import Item


def _make_aware_start(d):
    """Convert a date to a timezone-aware datetime at start of day."""
    return timezone.make_aware(datetime.combine(d, time.min))


def _make_aware_end(d):
    """Convert a date to a timezone-aware datetime at end of day."""
    return timezone.make_aware(datetime.combine(d, time.max))


def update_monthly_summary(year, month, user=None):
    """
    Update or create monthly summary for the given year/month.

    This function mirrors the logic in calculate_monthly_cashflow management
    command to ensure consistency between signal-triggered updates and
    batch recalculations.
    """
    from calendar import monthrange

    # Date range for this month
    start_date = date(year, month, 1)
    last_day = monthrange(year, month)[1]
    if month == 12:
        next_month_start = date(year + 1, 1, 1)
    else:
        next_month_start = date(year, month + 1, 1)

    # Timezone-aware datetimes for DateTimeField queries
    start_dt = _make_aware_start(start_date)
    end_dt = _make_aware_start(next_month_start)

    # ── Previous month summary ───────────────────────────────────────────
    if month == 1:
        prev_summary = MonthlyCashflowSummary.objects.filter(
            year=year - 1, month=12
        ).first()
    else:
        prev_summary = MonthlyCashflowSummary.objects.filter(
            year=year, month=month - 1
        ).first()

    # ══════════════════════════════════════════════════════════════════════
    # 1. INVENTORY (Formula-based: Closing = Opening + Purchased - COGS)
    # ══════════════════════════════════════════════════════════════════════
    inventory_purchased = _calculate_procurement_costs(start_date, next_month_start)
    cogs_actual = _calculate_actual_cogs(start_date, next_month_start, start_dt, end_dt)

    if prev_summary:
        inventory_opening = prev_summary.inventory_value_closing
    else:
        inventory_opening = Decimal('0')

    inventory_closing = inventory_opening + inventory_purchased - cogs_actual
    if inventory_closing < 0:
        inventory_closing = Decimal('0')

    # ══════════════════════════════════════════════════════════════════════
    # 2. ACCOUNTS RECEIVABLE
    # ══════════════════════════════════════════════════════════════════════
    ar_opening = _calculate_ar(start_date)
    ar_closing = _calculate_ar(next_month_start)
    ar_collections = _calculate_ar_collections(start_date, next_month_start)

    # ══════════════════════════════════════════════════════════════════════
    # 3. CASH FLOW (Cash Basis)
    # ══════════════════════════════════════════════════════════════════════
    cash_from_customers = _calculate_cash_from_customers(
        start_date, next_month_start, start_dt, end_dt
    )
    capital_injections = _calculate_capital_injections(start_date, next_month_start)
    other_cash_in = _calculate_other_cash_in(start_date, next_month_start)
    total_cash_in = cash_from_customers + capital_injections + other_cash_in

    cash_to_suppliers = inventory_purchased
    expenses_operational = _calculate_operational_expenses(start_date, next_month_start)
    expenses_other = _calculate_other_cash_out(start_date, next_month_start)
    total_cash_out = cash_to_suppliers + expenses_operational + expenses_other

    cash_opening = prev_summary.cash_closing if prev_summary else Decimal('0')
    net_cash_flow = total_cash_in - total_cash_out
    cash_closing = cash_opening + net_cash_flow

    # ══════════════════════════════════════════════════════════════════════
    # 4. P&L (Accrual Basis)
    # ══════════════════════════════════════════════════════════════════════
    revenue_sales = _calculate_sales_revenue(start_date, next_month_start, start_dt, end_dt)
    revenue_other = other_cash_in + capital_injections

    gross_profit = revenue_sales - cogs_actual
    gross_margin_pct = (
        (gross_profit / revenue_sales * 100) if revenue_sales > 0 else Decimal('0')
    )
    net_profit = gross_profit - expenses_operational - expenses_other

    # ══════════════════════════════════════════════════════════════════════
    # 5. BALANCE SHEET
    # ══════════════════════════════════════════════════════════════════════
    opening_balance = cash_opening + inventory_opening + ar_opening
    closing_balance = cash_closing + inventory_closing + ar_closing

    # ══════════════════════════════════════════════════════════════════════
    # 6. PERFORMANCE METRICS
    # ══════════════════════════════════════════════════════════════════════
    collection_rate_pct = (
        (cash_from_customers / revenue_sales * 100)
        if revenue_sales > 0 else Decimal('0')
    )
    dso = (
        (ar_closing / revenue_sales * last_day)
        if revenue_sales > 0 else Decimal('0')
    )
    avg_inventory = (inventory_opening + inventory_closing) / 2
    inventory_turnover = (
        (cogs_actual / avg_inventory) if avg_inventory > 0 else Decimal('0')
    )
    operating_cash_flow = cash_from_customers + other_cash_in - total_cash_out

    # ── Counts ───────────────────────────────────────────────────────────
    sales_count = _count_sales(start_dt, end_dt)
    procurement_count = GoodsReceipt.objects.filter(
        status=DocumentStatus.POSTED,
        receipt_date__gte=start_date,
        receipt_date__lt=next_month_start,
    ).count()
    expense_count = Expense.objects.filter(
        status='APPROVED',
        date__gte=start_date,
        date__lt=next_month_start,
    ).count()

    # ── Save ─────────────────────────────────────────────────────────────
    summary, created = MonthlyCashflowSummary.objects.update_or_create(
        year=year,
        month=month,
        defaults={
            'opening_balance': opening_balance,
            'closing_balance': closing_balance,
            'cash_opening': cash_opening,
            'cash_closing': cash_closing,
            'cash_from_customers': cash_from_customers,
            'cash_to_suppliers': cash_to_suppliers,
            'operating_cash_flow': operating_cash_flow,
            'inventory_value_opening': inventory_opening,
            'inventory_value_closing': inventory_closing,
            'inventory_purchased': inventory_purchased,
            'inventory_turnover': inventory_turnover,
            'cogs_actual': cogs_actual,
            'accounts_receivable_opening': ar_opening,
            'accounts_receivable_closing': ar_closing,
            'ar_collections': ar_collections,
            'revenue_accrual': revenue_sales,
            'gross_profit': gross_profit,
            'gross_margin_pct': gross_margin_pct,
            'net_profit': net_profit,
            'collection_rate_pct': collection_rate_pct,
            'days_sales_outstanding': dso,
            'capital_sales': revenue_sales,
            'capital_other': revenue_other,
            'capital_total': revenue_sales + revenue_other,
            'expenses_procurement': inventory_purchased,
            'expenses_operational': expenses_operational,
            'expenses_other': expenses_other,
            'expenses_total': cogs_actual + expenses_operational + expenses_other,
            'total_inflow': total_cash_in,
            'total_outflow': total_cash_out,
            'net_cash_flow': net_cash_flow,
            'sales_count': sales_count,
            'procurement_count': procurement_count,
            'expense_count': expense_count,
            'calculated_by': user,
            'calculated_at': timezone.now(),
        }
    )

    # ── Cascade to next month if its opening balance changed ─────────────
    if month == 12:
        next_year, next_month = year + 1, 1
    else:
        next_year, next_month = year, month + 1

    try:
        next_summary = MonthlyCashflowSummary.objects.get(
            year=next_year, month=next_month
        )
        if next_summary.opening_balance != closing_balance:
            update_monthly_summary(next_year, next_month, user=user)
    except MonthlyCashflowSummary.DoesNotExist:
        pass

    return summary


# ═══════════════════════════════════════════════════════════════════════════
# Shared Calculation Helpers (used by update_monthly_summary)
# ═══════════════════════════════════════════════════════════════════════════

def _calculate_inventory_value(as_of_date):
    """Calculate inventory value using StockMove history (historical snapshot)."""
    as_of_dt = _make_aware_end(as_of_date)
    total = Decimal('0')

    # IMPORTANT: Convert to set() — iterating a .distinct() values_list
    # queryset can still yield duplicates per underlying row.
    item_ids = set(
        StockMove.objects
        .filter(status=MoveStatus.POSTED, posted_at__lt=as_of_dt)
        .values_list('item_id', flat=True)
    )

    for item_id in item_ids:
        try:
            item = Item.objects.get(id=item_id)

            receives = StockMove.objects.filter(
                item_id=item_id, status=MoveStatus.POSTED, posted_at__lt=as_of_dt,
                move_type__in=[MoveType.RECEIVE, MoveType.RETURN_IN],
            ).aggregate(total=Coalesce(Sum('qty'), Decimal('0')))['total']

            delivers = StockMove.objects.filter(
                item_id=item_id, status=MoveStatus.POSTED, posted_at__lt=as_of_dt,
                move_type__in=[
                    MoveType.DELIVER, MoveType.POS_SALE, MoveType.SUPPLY_OUT,
                    MoveType.SERVICE_OUT, MoveType.DAMAGE, MoveType.RETURN_OUT,
                ],
            ).aggregate(total=Coalesce(Sum('qty'), Decimal('0')))['total']

            adjustments = StockMove.objects.filter(
                item_id=item_id, status=MoveStatus.POSTED, posted_at__lt=as_of_dt,
                move_type=MoveType.ADJUST,
            ).aggregate(total=Coalesce(Sum('qty'), Decimal('0')))['total']

            net_qty = receives - delivers + adjustments
            if net_qty > 0:
                avg_cost = _get_weighted_avg_cost(item, as_of_date)
                total += net_qty * avg_cost

        except Item.DoesNotExist:
            continue

    return total


def _get_weighted_avg_cost(item, as_of_date):
    """Get weighted average cost from GRN data."""
    from procurement.models import GoodsReceiptLine

    grn_lines = GoodsReceiptLine.objects.filter(
        item=item,
        goods_receipt__status=DocumentStatus.POSTED,
        goods_receipt__receipt_date__lt=as_of_date,
    ).select_related('goods_receipt__purchase_order')

    total_qty = Decimal('0')
    total_cost = Decimal('0')

    for grn_line in grn_lines:
        unit_price = Decimal('0')
        if grn_line.goods_receipt.purchase_order_id:
            po_line = grn_line.goods_receipt.purchase_order.lines.filter(
                item=item
            ).first()
            if po_line:
                unit_price = po_line.unit_price or Decimal('0')
        if unit_price == 0:
            unit_price = item.cost_price or Decimal('0')
        total_qty += grn_line.qty
        total_cost += grn_line.qty * unit_price

    if total_qty > 0:
        return total_cost / total_qty
    return item.cost_price or Decimal('0')


def _calculate_actual_cogs(start_date, end_date, start_dt, end_dt):
    """Calculate COGS from sales."""
    from core.cogs import pos_sale_cogs

    total = Decimal('0')

    for sale in POSSale.objects.filter(
        status=SaleStatus.POSTED, posted_at__gte=start_dt, posted_at__lt=end_dt,
    ).prefetch_related('lines__item', 'lines__unit', 'bundle_lines__price_list__items'):
        try:
            total += pos_sale_cogs(sale)
        except Exception:
            continue

    invoices = Invoice.objects.filter(
        is_void=False, date__gte=start_date, date__lt=end_date,
    )
    for inv in invoices:
        try:
            total += inv.grand_total_cogs or Decimal('0')
        except Exception:
            continue

    return total


def _calculate_sales_revenue(start_date, end_date, start_dt, end_dt):
    """Calculate total sales revenue (accrual basis)."""
    pos_rev = POSSale.objects.filter(
        status=SaleStatus.POSTED, posted_at__gte=start_dt, posted_at__lt=end_dt,
    ).aggregate(total=Coalesce(Sum('grand_total'), Decimal('0')))['total']

    inv_rev = Invoice.objects.filter(
        is_void=False, date__gte=start_date, date__lt=end_date,
    ).aggregate(total=Coalesce(Sum('grand_total'), Decimal('0')))['total']

    return pos_rev + inv_rev


def _calculate_cash_from_customers(start_date, end_date, start_dt, end_dt):
    """Calculate actual cash received from customers."""
    payments = InvoicePayment.objects.filter(
        date__gte=start_date, date__lt=end_date,
    ).aggregate(total=Coalesce(Sum('amount'), Decimal('0')))['total']

    pos_cash = POSSale.objects.filter(
        status=SaleStatus.POSTED, posted_at__gte=start_dt, posted_at__lt=end_dt,
    ).aggregate(total=Coalesce(Sum('grand_total'), Decimal('0')))['total']

    return payments + pos_cash


def _calculate_ar_collections(start_date, end_date):
    """Calculate AR collections (invoice payments only)."""
    return InvoicePayment.objects.filter(
        date__gte=start_date, date__lt=end_date,
    ).aggregate(total=Coalesce(Sum('amount'), Decimal('0')))['total']


def _calculate_ar(as_of_date):
    """Calculate accounts receivable as of date."""
    total = Decimal('0')
    for inv in Invoice.objects.filter(
        is_void=False, date__lt=as_of_date,
    ).prefetch_related('payments'):
        paid = sum(p.amount for p in inv.payments.filter(date__lt=as_of_date))
        balance = inv.grand_total - paid
        if balance > 0:
            total += balance
    return total


def _calculate_procurement_costs(start_date, end_date):
    """Calculate procurement costs including delivery charges."""
    total = Decimal('0')
    for grn in GoodsReceipt.objects.filter(
        status=DocumentStatus.POSTED,
        receipt_date__gte=start_date,
        receipt_date__lt=end_date,
    ).prefetch_related('lines__item', 'purchase_order__lines'):
        grn_total = Decimal('0')
        for line in grn.lines.all():
            line_cost = Decimal('0')
            if grn.purchase_order:
                po_line = grn.purchase_order.lines.filter(item=line.item).first()
                if po_line and po_line.unit_price > 0:
                    line_cost = line.qty * po_line.unit_price
            if line_cost == 0 and line.item.cost_price:
                line_cost = line.qty * line.item.cost_price
            grn_total += line_cost
        if grn.delivery_charge:
            grn_total += grn.delivery_charge
        total += grn_total
    return total


def _calculate_operational_expenses(start_date, end_date):
    """Calculate operational expenses from Expense model + CashFlowTransaction."""
    expense_total = Expense.objects.filter(
        status='APPROVED', date__gte=start_date, date__lt=end_date,
        category__is_cogs=False,
    ).aggregate(total=Coalesce(Sum('amount'), Decimal('0')))['total']

    cf_total = CashFlowTransaction.objects.filter(
        status=CashFlowStatus.APPROVED,
        flow_type=CashFlowType.CASH_OUT,
        category=CashFlowCategory.EXPENSES,
        transaction_date__gte=start_date,
        transaction_date__lt=end_date,
    ).aggregate(total=Coalesce(Sum('amount'), Decimal('0')))['total']

    return expense_total + cf_total


def _calculate_other_cash_in(start_date, end_date):
    """Calculate other cash-in (excluding sales and capital)."""
    return CashFlowTransaction.objects.filter(
        status=CashFlowStatus.APPROVED,
        flow_type=CashFlowType.CASH_IN,
        transaction_date__gte=start_date,
        transaction_date__lt=end_date,
    ).exclude(
        category__in=[CashFlowCategory.SALES, CashFlowCategory.CAPITAL]
    ).aggregate(total=Coalesce(Sum('amount'), Decimal('0')))['total']


def _calculate_other_cash_out(start_date, end_date):
    """Calculate other cash-out (excluding procurement, expenses, supplies)."""
    return CashFlowTransaction.objects.filter(
        status=CashFlowStatus.APPROVED,
        flow_type=CashFlowType.CASH_OUT,
        transaction_date__gte=start_date,
        transaction_date__lt=end_date,
    ).exclude(
        category__in=[
            CashFlowCategory.PROCUREMENT,
            CashFlowCategory.EXPENSES,
            CashFlowCategory.SUPPLIES,
        ]
    ).aggregate(total=Coalesce(Sum('amount'), Decimal('0')))['total']


def _calculate_capital_injections(start_date, end_date):
    """Calculate capital injections."""
    return CashFlowTransaction.objects.filter(
        status=CashFlowStatus.APPROVED,
        flow_type=CashFlowType.CASH_IN,
        category=CashFlowCategory.CAPITAL,
        transaction_date__gte=start_date,
        transaction_date__lt=end_date,
    ).aggregate(total=Coalesce(Sum('amount'), Decimal('0')))['total']


def _count_sales(start_dt, end_dt):
    """Count sales transactions."""
    return (
        POSSale.objects.filter(
            status=SaleStatus.POSTED, posted_at__gte=start_dt, posted_at__lt=end_dt,
        ).count()
        + DeliveryNote.objects.filter(
            status=DocumentStatus.POSTED, posted_at__gte=start_dt, posted_at__lt=end_dt,
        ).count()
        + SalesPickup.objects.filter(
            status=DocumentStatus.POSTED, posted_at__gte=start_dt, posted_at__lt=end_dt,
        ).count()
    )


# ═══════════════════════════════════════════════════════════════════════════
# Signal Handlers
# ═══════════════════════════════════════════════════════════════════════════

@receiver(post_save, sender=POSSale)
def update_summary_on_pos_sale(sender, instance, created, **kwargs):
    if instance.status == SaleStatus.POSTED and instance.created_at:
        update_monthly_summary(
            instance.created_at.year, instance.created_at.month,
            user=getattr(instance, 'created_by', None),
        )


@receiver(post_save, sender=Invoice)
def update_summary_on_invoice(sender, instance, created, **kwargs):
    if not instance.is_void and instance.paid_at:
        update_monthly_summary(
            instance.paid_at.year, instance.paid_at.month,
            user=getattr(instance, 'created_by', None),
        )


@receiver(post_save, sender=DeliveryNote)
def update_summary_on_delivery(sender, instance, created, **kwargs):
    if instance.status == DocumentStatus.POSTED and instance.posted_at:
        update_monthly_summary(
            instance.posted_at.year, instance.posted_at.month,
            user=getattr(instance, 'posted_by', None),
        )


@receiver(post_save, sender=SalesPickup)
def update_summary_on_pickup(sender, instance, created, **kwargs):
    if instance.status == DocumentStatus.POSTED and instance.posted_at:
        update_monthly_summary(
            instance.posted_at.year, instance.posted_at.month,
            user=getattr(instance, 'posted_by', None),
        )


@receiver(post_save, sender=GoodsReceipt)
def update_summary_on_grn(sender, instance, created, **kwargs):
    if instance.status == DocumentStatus.POSTED and instance.receipt_date:
        update_monthly_summary(
            instance.receipt_date.year, instance.receipt_date.month,
            user=getattr(instance, 'posted_by', None),
        )


@receiver(post_save, sender=Expense)
def update_summary_on_expense(sender, instance, created, **kwargs):
    if instance.status == 'APPROVED' and instance.date:
        update_monthly_summary(
            instance.date.year, instance.date.month,
            user=getattr(instance, 'created_by', None),
        )


@receiver(post_save, sender=CashFlowTransaction)
def update_summary_on_cashflow(sender, instance, created, **kwargs):
    if instance.status == CashFlowStatus.APPROVED and instance.transaction_date:
        update_monthly_summary(
            instance.transaction_date.year, instance.transaction_date.month,
            user=getattr(instance, 'approved_by', None),
        )


# ── Delete handlers ──────────────────────────────────────────────────────

@receiver(post_delete, sender=POSSale)
def recalc_on_pos_sale_delete(sender, instance, **kwargs):
    if instance.created_at:
        update_monthly_summary(instance.created_at.year, instance.created_at.month)


@receiver(post_delete, sender=Invoice)
def recalc_on_invoice_delete(sender, instance, **kwargs):
    if instance.paid_at:
        update_monthly_summary(instance.paid_at.year, instance.paid_at.month)


@receiver(post_delete, sender=GoodsReceipt)
def recalc_on_grn_delete(sender, instance, **kwargs):
    if instance.receipt_date:
        update_monthly_summary(instance.receipt_date.year, instance.receipt_date.month)


@receiver(post_delete, sender=Expense)
def recalc_on_expense_delete(sender, instance, **kwargs):
    if instance.date:
        update_monthly_summary(instance.date.year, instance.date.month)


@receiver(post_delete, sender=CashFlowTransaction)
def recalc_on_cashflow_delete(sender, instance, **kwargs):
    if instance.transaction_date:
        update_monthly_summary(
            instance.transaction_date.year, instance.transaction_date.month,
        )
