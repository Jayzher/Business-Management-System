from django.db import models
from django.conf import settings
from core.models import SoftDeleteModel, TimeStampedModel


class POSRegister(SoftDeleteModel):
    """Point-of-sale register / terminal."""
    name = models.CharField(max_length=100)
    warehouse = models.ForeignKey(
        'warehouses.Warehouse', on_delete=models.PROTECT, related_name='pos_registers',
    )
    default_location = models.ForeignKey(
        'warehouses.Location', on_delete=models.PROTECT, related_name='pos_registers',
    )
    price_list = models.ForeignKey(
        'pricing.PriceList', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='pos_registers',
    )
    receipt_footer = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.warehouse.code})"


class ShiftStatus(models.TextChoices):
    OPEN = 'OPEN', 'Open'
    CLOSED = 'CLOSED', 'Closed'


class POSShift(TimeStampedModel):
    """Cash shift for a register."""
    register = models.ForeignKey(POSRegister, on_delete=models.PROTECT, related_name='shifts')
    opened_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='pos_shifts_opened',
    )
    opened_at = models.DateTimeField()
    opening_cash = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='pos_shifts_closed',
    )
    closed_at = models.DateTimeField(null=True, blank=True)
    closing_cash_declared = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    status = models.CharField(max_length=10, choices=ShiftStatus.choices, default=ShiftStatus.OPEN)
    # Stored totals for speed
    cash_sales_total = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    noncash_sales_total = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    refund_total = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    cash_in_out_total = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    class Meta:
        ordering = ['-opened_at']

    def __str__(self):
        return f"Shift #{self.pk} @ {self.register.name} ({self.status})"

    @property
    def expected_cash(self):
        return self.opening_cash + self.cash_sales_total + self.cash_in_out_total - self.refund_total

    @property
    def variance(self):
        if self.status == ShiftStatus.CLOSED:
            return self.closing_cash_declared - self.expected_cash
        return None


class SaleStatus(models.TextChoices):
    DRAFT = 'DRAFT', 'Draft'
    PAID = 'PAID', 'Paid'
    POSTED = 'POSTED', 'Posted'
    VOID = 'VOID', 'Void'
    REFUNDED = 'REFUNDED', 'Refunded'


class POSSale(TimeStampedModel):
    """POS sale transaction."""
    sale_no = models.CharField(max_length=50, unique=True)
    register = models.ForeignKey(POSRegister, on_delete=models.PROTECT, related_name='sales')
    shift = models.ForeignKey(POSShift, on_delete=models.PROTECT, related_name='sales')
    warehouse = models.ForeignKey('warehouses.Warehouse', on_delete=models.PROTECT, related_name='pos_sales')
    location = models.ForeignKey('warehouses.Location', on_delete=models.PROTECT, related_name='pos_sales')
    customer = models.ForeignKey(
        'partners.Customer', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='pos_sales',
    )
    channel = models.ForeignKey(
        'core.SalesChannel', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='pos_sales',
        help_text='Sales channel (Physical Store, Facebook, etc.)',
    )
    status = models.CharField(max_length=10, choices=SaleStatus.choices, default=SaleStatus.DRAFT)
    subtotal = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    discount_total = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    tax_total = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    grand_total = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='pos_sales_created',
    )
    posted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='pos_sales_posted',
    )
    posted_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.sale_no} ({self.status})"


class POSSaleLine(models.Model):
    """POS sale line item."""
    sale = models.ForeignKey(POSSale, on_delete=models.CASCADE, related_name='lines')
    item = models.ForeignKey('catalog.Item', on_delete=models.PROTECT)
    location = models.ForeignKey(
        'warehouses.Location', on_delete=models.PROTECT, null=True, blank=True,
    )
    qty = models.DecimalField(max_digits=15, decimal_places=4)
    unit = models.ForeignKey('catalog.Unit', on_delete=models.PROTECT)
    unit_price = models.DecimalField(max_digits=15, decimal_places=4, default=0)
    discount_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    line_total = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    batch_number = models.CharField(max_length=100, blank=True, default='')
    serial_number = models.CharField(max_length=100, blank=True, default='')
    qr_uid_used = models.UUIDField(null=True, blank=True)

    def __str__(self):
        return f"POS Line: {self.item.code} x{self.qty}"


class PaymentMethod(models.TextChoices):
    CASH = 'CASH', 'Cash'
    GCASH = 'GCASH', 'GCash'
    BANK = 'BANK', 'Bank Transfer'
    CARD = 'CARD', 'Card'
    OTHER = 'OTHER', 'Other'


class POSPayment(TimeStampedModel):
    """Payment against a POS sale (supports split payments)."""
    sale = models.ForeignKey(POSSale, on_delete=models.CASCADE, related_name='payments')
    method = models.CharField(max_length=10, choices=PaymentMethod.choices)
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    reference_no = models.CharField(max_length=100, blank=True, default='')
    paid_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.method} {self.amount} for {self.sale.sale_no}"


class RefundStatus(models.TextChoices):
    DRAFT = 'DRAFT', 'Draft'
    POSTED = 'POSTED', 'Posted'
    CANCELLED = 'CANCELLED', 'Cancelled'


class POSRefund(TimeStampedModel):
    """POS refund header."""
    refund_no = models.CharField(max_length=50, unique=True)
    original_sale = models.ForeignKey(POSSale, on_delete=models.PROTECT, related_name='refunds')
    shift = models.ForeignKey(POSShift, on_delete=models.PROTECT, related_name='refunds')
    status = models.CharField(max_length=10, choices=RefundStatus.choices, default=RefundStatus.DRAFT)
    subtotal = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    tax_total = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    grand_total = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    reason = models.TextField(blank=True, default='')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='pos_refunds_created',
    )
    posted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='pos_refunds_posted',
    )
    posted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.refund_no} ({self.status})"


class POSRefundLine(models.Model):
    """POS refund line item."""
    refund = models.ForeignKey(POSRefund, on_delete=models.CASCADE, related_name='lines')
    sale_line = models.ForeignKey(POSSaleLine, on_delete=models.SET_NULL, null=True, blank=True)
    item = models.ForeignKey('catalog.Item', on_delete=models.PROTECT)
    location = models.ForeignKey('warehouses.Location', on_delete=models.PROTECT)
    qty = models.DecimalField(max_digits=15, decimal_places=4)
    unit = models.ForeignKey('catalog.Unit', on_delete=models.PROTECT)
    amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    def __str__(self):
        return f"Refund Line: {self.item.code} x{self.qty}"


class CashEntryType(models.TextChoices):
    CASH_IN = 'CASH_IN', 'Cash In'
    CASH_OUT = 'CASH_OUT', 'Cash Out'


class CashEntry(TimeStampedModel):
    """Cash in/out entries for a shift (non-sale cash movements)."""
    shift = models.ForeignKey(POSShift, on_delete=models.PROTECT, related_name='cash_entries')
    entry_type = models.CharField(max_length=10, choices=CashEntryType.choices)
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    reason = models.CharField(max_length=200)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='cash_entries',
    )

    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = 'cash entries'

    def __str__(self):
        return f"{self.entry_type} {self.amount} - {self.reason}"
