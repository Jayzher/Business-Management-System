from django.db import models
from django.conf import settings
from core.models import TimeStampedModel, SoftDeleteModel


class CashFlowCategory(models.TextChoices):
    PROCUREMENT = 'PROCUREMENT', 'Procurement'
    SALES = 'SALES', 'Sales'
    SUPPLIES = 'SUPPLIES', 'Supplies'
    EXPENSES = 'EXPENSES', 'Expenses'
    CAPITAL = 'CAPITAL', 'Capital'
    OTHER = 'OTHER', 'Other'


class CashFlowType(models.TextChoices):
    CASH_IN = 'CASH_IN', 'Cash In'
    CASH_OUT = 'CASH_OUT', 'Cash Out'


class CashFlowStatus(models.TextChoices):
    PENDING = 'PENDING', 'Pending'
    APPROVED = 'APPROVED', 'Approved'
    REJECTED = 'REJECTED', 'Rejected'
    CANCELLED = 'CANCELLED', 'Cancelled'


class PaymentMethod(models.TextChoices):
    CASH = 'CASH', 'Cash'
    CHECK = 'CHECK', 'Check'
    BANK_TRANSFER = 'BANK_TRANSFER', 'Bank Transfer'
    GCASH = 'GCASH', 'GCash'
    CARD = 'CARD', 'Card'
    OTHER = 'OTHER', 'Other'


class CashFlowTransaction(SoftDeleteModel):
    """Cash flow transaction — records money coming in or going out."""
    transaction_number = models.CharField(max_length=50, unique=True)
    category = models.CharField(
        max_length=20,
        choices=CashFlowCategory.choices,
        default=CashFlowCategory.OTHER,
        db_index=True,
    )
    flow_type = models.CharField(
        max_length=10,
        choices=CashFlowType.choices,
        db_index=True,
    )
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    transaction_date = models.DateField(db_index=True)
    payment_method = models.CharField(
        max_length=20,
        choices=PaymentMethod.choices,
        default=PaymentMethod.CASH,
    )
    reference_no = models.CharField(
        max_length=100, blank=True, default='',
        help_text='External reference number (e.g. receipt no, check no)',
    )
    reason = models.CharField(
        max_length=300,
        help_text='Brief reason or purpose for this transaction',
    )
    notes = models.TextField(blank=True, default='')
    status = models.CharField(
        max_length=20,
        choices=CashFlowStatus.choices,
        default=CashFlowStatus.PENDING,
        db_index=True,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='cashflow_created',
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='cashflow_approved',
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    rejected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='cashflow_rejected',
    )
    rejected_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.CharField(max_length=300, blank=True, default='')

    # Auto-generation tracking — links back to the source document
    source_type = models.CharField(
        max_length=50, blank=True, default='', db_index=True,
        help_text='Model class name of the originating document (e.g. GoodsReceipt, POSSale)',
    )
    source_id = models.PositiveIntegerField(
        null=True, blank=True, db_index=True,
        help_text='PK of the originating document',
    )
    is_auto_generated = models.BooleanField(
        default=False, db_index=True,
        help_text='True when this entry was created automatically by a system signal',
    )

    class Meta:
        ordering = ['-transaction_date', '-created_at']

    def __str__(self):
        return f"{self.transaction_number} ({self.get_flow_type_display()} - {self.get_category_display()})"

    @staticmethod
    def generate_next_number():
        """Generate the next sequential transaction number CF-XXXXXX."""
        from django.db.models import Max
        last = (
            CashFlowTransaction.all_objects
            .filter(transaction_number__startswith='CF-')
            .aggregate(max_num=Max('transaction_number'))
        )['max_num']
        if last:
            try:
                seq = int(last.replace('CF-', '')) + 1
            except ValueError:
                seq = 1
        else:
            seq = 1
        return f'CF-{seq:06d}'


class CashFlowLogAction(models.TextChoices):
    CREATED = 'CREATED', 'Created'
    UPDATED = 'UPDATED', 'Updated'
    APPROVED = 'APPROVED', 'Approved'
    REJECTED = 'REJECTED', 'Rejected'
    CANCELLED = 'CANCELLED', 'Cancelled'
    DELETED = 'DELETED', 'Deleted'


class CashFlowLog(TimeStampedModel):
    """Audit log for every action taken on a cash flow transaction."""
    transaction = models.ForeignKey(
        CashFlowTransaction,
        on_delete=models.CASCADE,
        related_name='logs',
    )
    action = models.CharField(max_length=20, choices=CashFlowLogAction.choices)
    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='cashflow_logs',
    )
    details = models.TextField(
        blank=True, default='',
        help_text='Human-readable description of what changed',
    )
    old_values = models.JSONField(null=True, blank=True)
    new_values = models.JSONField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.transaction.transaction_number} - {self.get_action_display()} by {self.performed_by}"


class MonthlyCashflowSummary(TimeStampedModel):
    """
    Monthly cashflow summary with opening/closing balance tracking.
    
    Formula:
    - Opening Balance = Previous month's closing balance
    - Total Inflow = Gross Profit from Sales + Other Cash-In
    - Total Outflow = Procurement Costs + Operational Expenses + Other Cash-Out
    - Net Cash Flow = Total Inflow - Total Outflow
    - Closing Balance = Opening Balance + Net Cash Flow
    """
    year = models.IntegerField(db_index=True)
    month = models.IntegerField(db_index=True)  # 1-12
    
    # ── Opening/Closing Balance ──────────────────────────────────────────────
    opening_balance = models.DecimalField(
        max_digits=15, decimal_places=2, default=0,
        help_text='Opening balance carried from previous month',
    )
    closing_balance = models.DecimalField(
        max_digits=15, decimal_places=2, default=0,
        help_text='Closing balance (opening + net cash flow)',
    )
    
    # ── Capital (Cash In) ────────────────────────────────────────────────────
    capital_sales = models.DecimalField(
        max_digits=15, decimal_places=2, default=0,
        help_text='Gross profit from sales (revenue - COGS)',
    )
    capital_other = models.DecimalField(
        max_digits=15, decimal_places=2, default=0,
        help_text='Other cash-in transactions (capital, investments)',
    )
    capital_total = models.DecimalField(
        max_digits=15, decimal_places=2, default=0,
        help_text='Total capital (sales + other cash-in)',
    )
    
    # ── Expenses (Cash Out) ──────────────────────────────────────────────────
    expenses_procurement = models.DecimalField(
        max_digits=15, decimal_places=2, default=0,
        help_text='Total procurement costs (GRN posted amounts)',
    )
    expenses_operational = models.DecimalField(
        max_digits=15, decimal_places=2, default=0,
        help_text='Operational expenses (utilities, salaries, etc.)',
    )
    expenses_other = models.DecimalField(
        max_digits=15, decimal_places=2, default=0,
        help_text='Other cash-out transactions',
    )
    expenses_total = models.DecimalField(
        max_digits=15, decimal_places=2, default=0,
        help_text='Total expenses (procurement + operational + other)',
    )
    
    # ── Totals & Net Flow ────────────────────────────────────────────────────
    total_inflow = models.DecimalField(
        max_digits=15, decimal_places=2, default=0,
        help_text='Total cash inflow (capital_total)',
    )
    total_outflow = models.DecimalField(
        max_digits=15, decimal_places=2, default=0,
        help_text='Total cash outflow (expenses_total)',
    )
    net_cash_flow = models.DecimalField(
        max_digits=15, decimal_places=2, default=0,
        help_text='Net cash flow (total_inflow - total_outflow)',
    )
    net_profit = models.DecimalField(
        max_digits=15, decimal_places=2, default=0,
        help_text='Net profit (capital - expenses) - DEPRECATED, use net_cash_flow',
    )
    
    # ── Metadata ─────────────────────────────────────────────────────────────
    sales_count = models.IntegerField(default=0, help_text='Number of sales transactions')
    procurement_count = models.IntegerField(default=0, help_text='Number of procurement transactions')
    expense_count = models.IntegerField(default=0, help_text='Number of expense records')
    
    notes = models.TextField(
        blank=True, default='',
        help_text='Additional notes or adjustments',
    )
    
    calculated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='monthly_summaries_calculated',
    )
    calculated_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-year', '-month']
        unique_together = [('year', 'month')]
        verbose_name = 'Monthly Cashflow Summary'
        verbose_name_plural = 'Monthly Cashflow Summaries'
    
    def __str__(self):
        from calendar import month_name
        return f"{month_name[self.month]} {self.year}"
    
    @property
    def month_name(self):
        from calendar import month_name
        return month_name[self.month]
    
    @property
    def profit_margin(self):
        """Calculate profit margin percentage."""
        if self.capital_total > 0:
            return (self.net_profit / self.capital_total) * 100
        return 0

