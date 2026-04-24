"""
Monthly Cashflow Signals
=========================
Automatically update monthly cashflow summaries when transactions occur.
"""
from decimal import Decimal
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.db.models import Sum
from django.utils import timezone

from cashflow.models import MonthlyCashflowSummary, CashFlowTransaction, CashFlowType, CashFlowStatus, CashFlowCategory
from core.models import Expense, Invoice, DocumentStatus
from pos.models import POSSale, SaleStatus
from sales.models import DeliveryNote, SalesPickup
from procurement.models import GoodsReceipt


def update_monthly_summary(year, month, user=None):
    """
    Update or create monthly summary for the given year/month.
    This is called by all signals to keep summaries up-to-date.
    """
    from datetime import date
    
    # Date range for this month
    if month == 12:
        next_month = date(year + 1, 1, 1)
    else:
        next_month = date(year, month + 1, 1)
    start_date = date(year, month, 1)
    end_date = next_month
    
    # ── Calculate Capital (Cash In) ──────────────────────────────────────
    # Sales Gross Profit
    capital_sales = Decimal('0')
    
    # POS Sales - calculate COGS from sale lines
    from core.cogs import pos_sale_cogs
    pos_sales = POSSale.objects.filter(
        status=SaleStatus.POSTED,
        created_at__gte=start_date,
        created_at__lt=end_date,
    ).prefetch_related('lines__item', 'lines__unit', 'bundle_lines__price_list__items')
    
    for sale in pos_sales:
        try:
            revenue = sale.grand_total or Decimal('0')
            cogs = pos_sale_cogs(sale)
            gross_profit = revenue - cogs
            capital_sales += gross_profit
        except Exception:
            # Skip sales with missing items, use revenue only
            capital_sales += (sale.grand_total or Decimal('0'))
            continue
    
    # Invoices - use stored grand_total_cogs
    invoices = Invoice.objects.filter(
        is_void=False,
        paid_at__gte=start_date,
        paid_at__lt=end_date,
    )
    for inv in invoices:
        try:
            gross_profit = (inv.grand_total or Decimal('0')) - (inv.grand_total_cogs or Decimal('0'))
            capital_sales += gross_profit
        except Exception:
            # Skip invoices with errors
            continue
    
    # Other Cash-In
    result = CashFlowTransaction.objects.filter(
        status=CashFlowStatus.APPROVED,
        flow_type=CashFlowType.CASH_IN,
        transaction_date__gte=start_date,
        transaction_date__lt=end_date,
    ).exclude(
        category=CashFlowCategory.SALES
    ).aggregate(total=Sum('amount'))
    capital_other = result['total'] or Decimal('0')
    
    capital_total = capital_sales + capital_other
    
    # ── Calculate Expenses (Cash Out) ────────────────────────────────────
    # Procurement Costs (for tracking cash flow, NOT for P&L expense)
    expenses_procurement = Decimal('0')
    grns = GoodsReceipt.objects.filter(
        status=DocumentStatus.POSTED,
        receipt_date__gte=start_date,
        receipt_date__lt=end_date,
    ).prefetch_related('lines', 'purchase_order__lines')
    
    for grn in grns:
        try:
            for line in grn.lines.all():
                try:
                    if grn.purchase_order:
                        po_line = grn.purchase_order.lines.filter(item=line.item).first()
                        if po_line:
                            cost = line.qty * po_line.unit_price
                            expenses_procurement += cost
                except Exception:
                    # Skip lines with missing items
                    continue
        except Exception:
            # Skip GRNs with errors
            continue
    
    # ── Calculate COGS (Actual Expense) ──────────────────────────────────
    # COGS = Cost of inventory actually SOLD (not purchased)
    cogs_actual = Decimal('0')
    
    # POS Sales COGS (already calculated above, recalculate for expense tracking)
    for sale in pos_sales:
        try:
            cogs = pos_sale_cogs(sale)
            cogs_actual += cogs
        except Exception:
            continue
    
    # Invoice COGS
    for inv in invoices:
        try:
            cogs_actual += inv.grand_total_cogs or Decimal('0')
        except Exception:
            continue
    
    # Operational Expenses (exclude COGS/procurement expenses)
    result = Expense.objects.filter(
        status='APPROVED',
        date__gte=start_date,
        date__lt=end_date,
        category__is_cogs=False,  # Exclude procurement/COGS expenses
    ).aggregate(total=Sum('amount'))
    expenses_operational = result['total'] or Decimal('0')
    
    # Other Cash-Out
    result = CashFlowTransaction.objects.filter(
        status=CashFlowStatus.APPROVED,
        flow_type=CashFlowType.CASH_OUT,
        transaction_date__gte=start_date,
        transaction_date__lt=end_date,
    ).exclude(
        category__in=[CashFlowCategory.PROCUREMENT, CashFlowCategory.EXPENSES]
    ).aggregate(total=Sum('amount'))
    expenses_other = result['total'] or Decimal('0')
    
    # ✅ FIX: Cash expenses = actual cash spent (procurement + operational + other)
    cash_expenses_total = expenses_procurement + expenses_operational + expenses_other
    
    # P&L expenses = COGS + operational + other (for profit calculation)
    expenses_total = cogs_actual + expenses_operational + expenses_other
    
    # ── Calculate Totals & Net Flow ──────────────────────────────────────
    total_inflow = capital_total
    total_outflow = cash_expenses_total  # ✅ FIX: Use cash expenses (includes procurement)
    net_cash_flow = total_inflow - total_outflow
    
    # Net profit uses P&L expenses (COGS-based)
    net_profit = capital_total - expenses_total
    
    # ── Get Opening Balance from Previous Month ──────────────────────────
    opening_balance = Decimal('0')
    if month == 1:
        # January - get from December of previous year
        try:
            prev_summary = MonthlyCashflowSummary.objects.get(year=year-1, month=12)
            opening_balance = prev_summary.closing_balance
        except MonthlyCashflowSummary.DoesNotExist:
            opening_balance = Decimal('0')
    else:
        # Get from previous month of same year
        try:
            prev_summary = MonthlyCashflowSummary.objects.get(year=year, month=month-1)
            opening_balance = prev_summary.closing_balance
        except MonthlyCashflowSummary.DoesNotExist:
            opening_balance = Decimal('0')
    
    # ── Calculate Closing Balance ────────────────────────────────────────
    closing_balance = opening_balance + net_cash_flow
    
    # ── Get counts ───────────────────────────────────────────────────────
    sales_count = (
        POSSale.objects.filter(
            status=SaleStatus.POSTED,
            created_at__gte=start_date,
            created_at__lt=end_date,
        ).count() +
        DeliveryNote.objects.filter(
            status=DocumentStatus.POSTED,
            posted_at__gte=start_date,
            posted_at__lt=end_date,
        ).count() +
        SalesPickup.objects.filter(
            status=DocumentStatus.POSTED,
            posted_at__gte=start_date,
            posted_at__lt=end_date,
        ).count()
    )
    
    procurement_count = GoodsReceipt.objects.filter(
        status=DocumentStatus.POSTED,
        receipt_date__gte=start_date,
        receipt_date__lt=end_date,
    ).count()
    
    expense_count = Expense.objects.filter(
        status='APPROVED',
        date__gte=start_date,
        date__lt=end_date,
    ).count()
    
    # ── Save or update summary ───────────────────────────────────────────
    summary, created = MonthlyCashflowSummary.objects.update_or_create(
        year=year,
        month=month,
        defaults={
            'opening_balance': opening_balance,
            'capital_sales': capital_sales,
            'capital_other': capital_other,
            'capital_total': capital_total,
            'cogs_actual': cogs_actual,  # ✅ Save COGS for P&L tracking
            'expenses_procurement': expenses_procurement,  # Keep for cash flow tracking
            'expenses_operational': expenses_operational,
            'expenses_other': expenses_other,
            'expenses_total': expenses_total,  # P&L expenses (COGS-based)
            'total_inflow': total_inflow,
            'total_outflow': total_outflow,  # ✅ FIX: Now uses cash expenses
            'net_cash_flow': net_cash_flow,  # ✅ FIX: Now reflects actual cash movement
            'closing_balance': closing_balance,
            'net_profit': net_profit,
            'sales_count': sales_count,
            'procurement_count': procurement_count,
            'expense_count': expense_count,
            'calculated_by': user,
            'calculated_at': timezone.now(),
        }
    )
    
    # ── Update Next Month's Opening Balance ──────────────────────────────
    # When this month's closing balance changes, update next month's opening
    if month == 12:
        next_year, next_month = year + 1, 1
    else:
        next_year, next_month = year, month + 1
    
    try:
        next_summary = MonthlyCashflowSummary.objects.get(year=next_year, month=next_month)
        if next_summary.opening_balance != closing_balance:
            # Recalculate next month to cascade the balance change
            update_monthly_summary(next_year, next_month, user=user)
    except MonthlyCashflowSummary.DoesNotExist:
        # Next month doesn't exist yet, that's fine
        pass
    
    return summary


# ═══════════════════════════════════════════════════════════════════════════
# Signal Handlers
# ═══════════════════════════════════════════════════════════════════════════

@receiver(post_save, sender=POSSale)
def update_summary_on_pos_sale(sender, instance, created, **kwargs):
    """Update monthly summary when POS sale is posted."""
    if instance.status == SaleStatus.POSTED and instance.created_at:
        update_monthly_summary(
            instance.created_at.year,
            instance.created_at.month,
            user=getattr(instance, 'created_by', None)
        )


@receiver(post_save, sender=Invoice)
def update_summary_on_invoice(sender, instance, created, **kwargs):
    """Update monthly summary when invoice is paid."""
    if not instance.is_void and instance.paid_at:
        update_monthly_summary(
            instance.paid_at.year,
            instance.paid_at.month,
            user=getattr(instance, 'created_by', None)
        )


@receiver(post_save, sender=DeliveryNote)
def update_summary_on_delivery(sender, instance, created, **kwargs):
    """Update monthly summary when delivery note is posted."""
    if instance.status == DocumentStatus.POSTED and instance.posted_at:
        update_monthly_summary(
            instance.posted_at.year,
            instance.posted_at.month,
            user=getattr(instance, 'posted_by', None)
        )


@receiver(post_save, sender=SalesPickup)
def update_summary_on_pickup(sender, instance, created, **kwargs):
    """Update monthly summary when pickup is posted."""
    if instance.status == DocumentStatus.POSTED and instance.posted_at:
        update_monthly_summary(
            instance.posted_at.year,
            instance.posted_at.month,
            user=getattr(instance, 'posted_by', None)
        )


@receiver(post_save, sender=GoodsReceipt)
def update_summary_on_grn(sender, instance, created, **kwargs):
    """Update monthly summary when GRN is posted."""
    if instance.status == DocumentStatus.POSTED and instance.receipt_date:
        update_monthly_summary(
            instance.receipt_date.year,
            instance.receipt_date.month,
            user=getattr(instance, 'posted_by', None)
        )


@receiver(post_save, sender=Expense)
def update_summary_on_expense(sender, instance, created, **kwargs):
    """Update monthly summary when expense is approved."""
    if instance.status == 'APPROVED' and instance.date:
        update_monthly_summary(
            instance.date.year,
            instance.date.month,
            user=getattr(instance, 'created_by', None)
        )


@receiver(post_save, sender=CashFlowTransaction)
def update_summary_on_cashflow(sender, instance, created, **kwargs):
    """Update monthly summary when cashflow transaction is approved."""
    if instance.status == CashFlowStatus.APPROVED and instance.transaction_date:
        update_monthly_summary(
            instance.transaction_date.year,
            instance.transaction_date.month,
            user=getattr(instance, 'approved_by', None)
        )


# ── Delete handlers (recalculate when records are deleted) ──────────────────

@receiver(post_delete, sender=POSSale)
def recalc_on_pos_sale_delete(sender, instance, **kwargs):
    """Recalculate monthly summary when POS sale is deleted."""
    if instance.created_at:
        update_monthly_summary(instance.created_at.year, instance.created_at.month)


@receiver(post_delete, sender=Invoice)
def recalc_on_invoice_delete(sender, instance, **kwargs):
    """Recalculate monthly summary when invoice is deleted."""
    if instance.paid_at:
        update_monthly_summary(instance.paid_at.year, instance.paid_at.month)


@receiver(post_delete, sender=GoodsReceipt)
def recalc_on_grn_delete(sender, instance, **kwargs):
    """Recalculate monthly summary when GRN is deleted."""
    if instance.receipt_date:
        update_monthly_summary(instance.receipt_date.year, instance.receipt_date.month)


@receiver(post_delete, sender=Expense)
def recalc_on_expense_delete(sender, instance, **kwargs):
    """Recalculate monthly summary when expense is deleted."""
    if instance.date:
        update_monthly_summary(instance.date.year, instance.date.month)


@receiver(post_delete, sender=CashFlowTransaction)
def recalc_on_cashflow_delete(sender, instance, **kwargs):
    """Recalculate monthly summary when cashflow transaction is deleted."""
    if instance.transaction_date:
        update_monthly_summary(instance.transaction_date.year, instance.transaction_date.month)
