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
    
    # POS Sales
    pos_sales = POSSale.objects.filter(
        status=SaleStatus.POSTED,
        created_at__gte=start_date,
        created_at__lt=end_date,
    )
    for sale in pos_sales:
        gross_profit = (sale.grand_total or Decimal('0')) - (sale.grand_total_cogs or Decimal('0'))
        capital_sales += gross_profit
    
    # Invoices
    invoices = Invoice.objects.filter(
        is_void=False,
        paid_at__gte=start_date,
        paid_at__lt=end_date,
    )
    for inv in invoices:
        gross_profit = (inv.grand_total or Decimal('0')) - (inv.grand_total_cogs or Decimal('0'))
        capital_sales += gross_profit
    
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
    # Procurement Costs
    expenses_procurement = Decimal('0')
    grns = GoodsReceipt.objects.filter(
        status=DocumentStatus.POSTED,
        receipt_date__gte=start_date,
        receipt_date__lt=end_date,
    ).prefetch_related('lines', 'purchase_order__lines')
    
    for grn in grns:
        for line in grn.lines.all():
            if grn.purchase_order:
                po_line = grn.purchase_order.lines.filter(item=line.item).first()
                if po_line:
                    cost = line.qty * po_line.unit_price
                    expenses_procurement += cost
    
    # Operational Expenses
    result = Expense.objects.filter(
        status='APPROVED',
        date__gte=start_date,
        date__lt=end_date,
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
    
    expenses_total = expenses_procurement + expenses_operational + expenses_other
    
    # ── Calculate Net Profit ─────────────────────────────────────────────
    net_profit = capital_total - expenses_total
    
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
            'capital_sales': capital_sales,
            'capital_other': capital_other,
            'capital_total': capital_total,
            'expenses_procurement': expenses_procurement,
            'expenses_operational': expenses_operational,
            'expenses_other': expenses_other,
            'expenses_total': expenses_total,
            'net_profit': net_profit,
            'sales_count': sales_count,
            'procurement_count': procurement_count,
            'expense_count': expense_count,
            'calculated_by': user,
            'calculated_at': timezone.now(),
        }
    )
    
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
