from decimal import Decimal
from django.db import models
from django.conf import settings


class ServiceStatus(models.TextChoices):
    DRAFT = 'DRAFT', 'Draft'
    IN_PROGRESS = 'IN_PROGRESS', 'In Progress'
    COMPLETED = 'COMPLETED', 'Completed'
    CANCELLED = 'CANCELLED', 'Cancelled'


class ServicePaymentStatus(models.TextChoices):
    UNPAID = 'UNPAID', 'Unpaid'
    PARTIAL = 'PARTIAL', 'Partially Paid'
    PAID = 'PAID', 'Paid'


class DiscountType(models.TextChoices):
    FIXED = 'FIXED', 'Fixed Amount (₱)'
    PERCENT = 'PERCENT', 'Percentage (%)'


class CustomerService(models.Model):
    """Customer service / job order record."""
    service_number = models.CharField(max_length=50, unique=True)
    service_name = models.CharField(max_length=200)
    customer_name = models.CharField(max_length=200, help_text='Customer name (free text)')
    service_date = models.DateField()
    completion_date = models.DateField(
        null=True, blank=True,
        help_text='Date the service was completed (set when marking as Completed)',
    )
    address = models.TextField(blank=True, default='')
    notes = models.TextField(blank=True, default='')
    status = models.CharField(
        max_length=20,
        choices=ServiceStatus.choices,
        default=ServiceStatus.DRAFT,
        db_index=True,
    )
    payment_status = models.CharField(
        max_length=20,
        choices=ServicePaymentStatus.choices,
        default=ServicePaymentStatus.UNPAID,
        db_index=True,
    )
    amount = models.DecimalField(
        max_digits=15, decimal_places=2,
        null=True, blank=True,
        help_text='Legacy manual override — use service_fee instead.',
    )
    service_fee = models.DecimalField(
        max_digits=15, decimal_places=2,
        null=True, blank=True, default=None,
        help_text='Service / labor charge added on top of product & material lines.',
    )
    discount_type = models.CharField(
        max_length=10,
        choices=DiscountType.choices,
        default=DiscountType.FIXED,
    )
    discount_value = models.DecimalField(
        max_digits=15, decimal_places=2,
        default=Decimal('0'),
        help_text='Discount: fixed ₱ amount or percentage of subtotal.',
    )
    warehouse = models.ForeignKey(
        'warehouses.Warehouse',
        on_delete=models.PROTECT,
        related_name='customer_services',
        null=True, blank=True,
        help_text='Warehouse to deduct parts from when completed',
    )
    invoice = models.ForeignKey(
        'core.Invoice',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='customer_services',
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='services_created',
    )
    posted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='services_completed',
    )
    posted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Customer Service'
        verbose_name_plural = 'Customer Services'

    def __str__(self):
        return f"{self.service_number} — {self.service_name}"

    @property
    def product_lines_total(self):
        return sum((line.line_total for line in self.lines.all()), Decimal('0'))

    @property
    def other_materials_total(self):
        return sum((mat.line_total for mat in self.other_materials.all()), Decimal('0'))

    @property
    def line_total(self):
        """Backward-compat alias for product_lines_total."""
        return self.product_lines_total

    @property
    def service_fee_amount(self):
        return self.service_fee or Decimal('0')

    @property
    def subtotal(self):
        """Sum of product lines + other materials + service fee (before discount)."""
        return self.product_lines_total + self.other_materials_total + self.service_fee_amount

    @property
    def discount_amount(self):
        """Computed discount based on discount_type and discount_value."""
        val = self.discount_value or Decimal('0')
        if self.discount_type == DiscountType.PERCENT:
            return (self.subtotal * val / Decimal('100')).quantize(Decimal('0.01'))
        return val

    @property
    def grand_total(self):
        return self.subtotal - self.discount_amount


class ServiceLine(models.Model):
    """Product / part line for a Customer Service record."""
    service = models.ForeignKey(
        CustomerService, on_delete=models.CASCADE, related_name='lines',
    )
    item = models.ForeignKey('catalog.Item', on_delete=models.PROTECT)
    location = models.ForeignKey(
        'warehouses.Location', on_delete=models.PROTECT,
        null=True, blank=True,
    )
    qty = models.DecimalField(max_digits=15, decimal_places=4)
    unit = models.ForeignKey('catalog.Unit', on_delete=models.PROTECT)
    unit_price = models.DecimalField(
        max_digits=15, decimal_places=4, default=0,
        help_text='Selling price per unit (auto-filled from Item catalog)',
    )
    notes = models.TextField(blank=True, default='')

    @property
    def line_total(self):
        return self.qty * self.unit_price

    def __str__(self):
        return f"SvcLine: {self.item.code} x{self.qty}"


class ServiceOtherMaterial(models.Model):
    """Free-text other material / supply line for a Customer Service."""
    service = models.ForeignKey(
        CustomerService, on_delete=models.CASCADE, related_name='other_materials',
    )
    item_name = models.CharField(max_length=200, help_text='Material or supply description')
    qty = models.DecimalField(max_digits=15, decimal_places=4)
    unit_price = models.DecimalField(
        max_digits=15, decimal_places=4, default=0,
        help_text='Price charged per unit',
    )
    vendor = models.CharField(max_length=200, blank=True, default='')
    notes = models.CharField(max_length=255, blank=True, default='')

    @property
    def line_total(self):
        return self.qty * self.unit_price

    def __str__(self):
        return f"OtherMat: {self.item_name} x{self.qty}"
