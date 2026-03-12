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
        help_text='Optional manual service fee (overrides product line total)',
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
    def line_total(self):
        return sum((line.line_total for line in self.lines.all()), Decimal('0'))

    @property
    def grand_total(self):
        if self.amount is not None:
            return self.amount
        return self.line_total


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
        help_text='Auto-filled from Item catalog selling price',
    )
    notes = models.TextField(blank=True, default='')

    @property
    def line_total(self):
        return self.qty * self.unit_price

    def __str__(self):
        return f"SvcLine: {self.item.code} x{self.qty}"
