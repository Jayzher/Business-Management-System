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
    partial_payment_amount = models.DecimalField(
        max_digits=15, decimal_places=2,
        null=True, blank=True, default=Decimal('0'),
        help_text='Amount already paid by the customer when payment status is Partially Paid.',
    )
    amount = models.DecimalField(
        max_digits=15, decimal_places=2,
        null=True, blank=True,
        help_text='Legacy manual override — use service_fee instead.',
    )
    quotation = models.DecimalField(
        max_digits=15, decimal_places=2,
        null=True, blank=True, default=None,
        help_text='Total amount quoted to the customer for this service.',
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
    def quotation_amount(self):
        return self.quotation or Decimal('0')

    @property
    def bundles_total(self):
        return sum((b.bundle_total for b in self.bundles.all()), Decimal('0'))

    @property
    def subtotal(self):
        """Quotation minus product-line, other-material, and bundle costs (before discount)."""
        return self.quotation_amount - self.product_lines_total - self.other_materials_total - self.bundles_total

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

    @property
    def partial_payment_amount_value(self):
        return self.partial_payment_amount or Decimal('0')

    @property
    def remaining_balance(self):
        return max(self.grand_total - self.partial_payment_amount_value, Decimal('0'))


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
        return (self.qty or 0) * (self.unit_price or 0)

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
        return (self.qty or 0) * (self.unit_price or 0)

    def __str__(self):
        return f"OtherMat: {self.item_name} x{self.qty}"


class ServiceBundle(models.Model):
    """A PriceList bundle applied to a Customer Service as a COGS cost.
    qty = how many full sets of this bundle are used."""
    service = models.ForeignKey(
        CustomerService, on_delete=models.CASCADE, related_name='bundles',
    )
    price_list = models.ForeignKey(
        'pricing.PriceList', on_delete=models.PROTECT, related_name='service_bundle_lines',
    )
    qty = models.DecimalField(
        max_digits=10, decimal_places=2, default=1,
        help_text='Number of full bundle sets.',
    )

    @property
    def bundle_unit_price(self):
        """Sum of all PriceListItem prices in this bundle (one set)."""
        if not self.price_list_id:
            return Decimal('0')
        return sum(
            ((pli.price or Decimal('0')) for pli in self.price_list.items.all()),
            Decimal('0'),
        )

    @property
    def bundle_total(self):
        return self.bundle_unit_price * (self.qty or Decimal('0'))

    def __str__(self):
        return f"Bundle: {self.price_list.name} ×{self.qty}"
