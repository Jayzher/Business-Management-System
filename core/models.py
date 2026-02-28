import uuid
from django.db import models
from django.conf import settings


class TimeStampedModel(models.Model):
    """Abstract base: created_at / updated_at on every model."""
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class SoftDeleteManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(is_active=True)


class SoftDeleteModel(TimeStampedModel):
    """Abstract base with soft-delete support."""
    is_active = models.BooleanField(default=True, db_index=True)

    objects = SoftDeleteManager()
    all_objects = models.Manager()

    def soft_delete(self):
        self.is_active = False
        self.save(update_fields=['is_active', 'updated_at'])

    def restore(self):
        self.is_active = True
        self.save(update_fields=['is_active', 'updated_at'])

    class Meta:
        abstract = True


class DocumentStatus(models.TextChoices):
    DRAFT = 'DRAFT', 'Draft'
    APPROVED = 'APPROVED', 'Approved'
    POSTED = 'POSTED', 'Posted'
    CANCELLED = 'CANCELLED', 'Cancelled'


class TransactionalDocument(SoftDeleteModel):
    """Abstract base for PO, GRN, SO, Delivery, Transfer, Adjustment, etc."""
    document_number = models.CharField(max_length=50, unique=True)
    status = models.CharField(
        max_length=20,
        choices=DocumentStatus.choices,
        default=DocumentStatus.DRAFT,
        db_index=True,
    )
    notes = models.TextField(blank=True, default='')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='%(class)s_created',
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='%(class)s_approved',
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    posted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='%(class)s_posted',
    )
    posted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        abstract = True

    def __str__(self):
        return f"{self.document_number} ({self.status})"


class BusinessProfile(models.Model):
    """Singleton business profile — Settings page."""
    name = models.CharField(max_length=200, help_text='Business / Store name')
    tagline = models.CharField(max_length=300, blank=True, default='')
    owner_name = models.CharField(max_length=200, blank=True, default='')
    email = models.EmailField(blank=True, default='')
    phone = models.CharField(max_length=30, blank=True, default='')
    address = models.TextField(blank=True, default='')
    city = models.CharField(max_length=100, blank=True, default='')
    province = models.CharField(max_length=100, blank=True, default='')
    zip_code = models.CharField(max_length=10, blank=True, default='')
    country = models.CharField(max_length=100, default='Philippines')
    tin = models.CharField(max_length=30, blank=True, default='', verbose_name='TIN')
    logo = models.ImageField(upload_to='business/', blank=True, null=True)
    currency = models.CharField(max_length=10, default='PHP')
    fiscal_year_start_month = models.PositiveSmallIntegerField(
        default=1, help_text='Month number (1=Jan … 12=Dec)'
    )
    receipt_footer = models.TextField(blank=True, default='', help_text='Printed at the bottom of receipts/invoices')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Business Profile'
        verbose_name_plural = 'Business Profile'

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        # Singleton: ensure only one row exists
        if not self.pk and BusinessProfile.objects.exists():
            existing = BusinessProfile.objects.first()
            self.pk = existing.pk
        super().save(*args, **kwargs)

    @classmethod
    def get_instance(cls):
        obj, _ = cls.objects.get_or_create(
            pk=1, defaults={'name': 'My Business'}
        )
        return obj


class SalesChannel(SoftDeleteModel):
    """Sales channel master (Physical Store, Facebook, Shopee, etc.)."""
    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=30, unique=True)
    description = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class ExpenseCategory(SoftDeleteModel):
    """Expense categories (COGS, Admin, Operational, Payroll, etc.)."""
    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=30, unique=True)
    description = models.TextField(blank=True, default='')
    is_cogs = models.BooleanField(
        default=False,
        help_text='If True, amounts are treated as Cost of Goods Sold in financial statements.'
    )

    class Meta:
        verbose_name_plural = 'Expense categories'
        ordering = ['name']

    def __str__(self):
        return self.name


class ExpenseStatus(models.TextChoices):
    PENDING = 'PENDING', 'Pending'
    APPROVED = 'APPROVED', 'Approved'
    PAID = 'PAID', 'Paid'
    CANCELLED = 'CANCELLED', 'Cancelled'


class Expense(TimeStampedModel):
    """Expense transaction record."""
    date = models.DateField(db_index=True)
    category = models.ForeignKey(
        ExpenseCategory, on_delete=models.PROTECT, related_name='expenses'
    )
    item_description = models.CharField(max_length=300, blank=True, default='', help_text='Item or service description')
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    status = models.CharField(
        max_length=20, choices=ExpenseStatus.choices,
        default=ExpenseStatus.PAID, db_index=True,
    )
    vendor = models.CharField(max_length=200, blank=True, default='')
    business_address = models.TextField(blank=True, default='', help_text='Vendor business address')
    reference_no = models.CharField(max_length=100, blank=True, default='')
    receipt_photo = models.ImageField(upload_to='expenses/receipts/', blank=True, null=True)
    memo = models.TextField(blank=True, default='')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='expenses_created',
    )

    class Meta:
        ordering = ['-date', '-created_at']

    def __str__(self):
        return f"{self.date} | {self.category.name} | {self.amount}"


class Invoice(TimeStampedModel):
    """Invoice generated from a POS Sale or Sales Order."""
    invoice_number = models.CharField(max_length=50, unique=True)
    date = models.DateField()
    due_date = models.DateField(null=True, blank=True)
    pos_sale = models.ForeignKey(
        'pos.POSSale', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='invoices',
    )
    sales_order = models.ForeignKey(
        'sales.SalesOrder', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='invoices',
    )
    customer_name = models.CharField(max_length=200, blank=True, default='')
    customer_address = models.TextField(blank=True, default='')
    customer_tin = models.CharField(max_length=30, blank=True, default='')
    subtotal = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    discount_total = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    tax_total = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    grand_total = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    notes = models.TextField(blank=True, default='')
    is_paid = models.BooleanField(default=False)
    paid_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='invoices_created',
    )

    class Meta:
        ordering = ['-date', '-created_at']

    def __str__(self):
        return f"INV-{self.invoice_number}"


class PaymentMethod(models.TextChoices):
    CASH = 'CASH', 'Cash'
    CHECK = 'CHECK', 'Check'
    BANK_TRANSFER = 'BANK_TRANSFER', 'Bank Transfer'
    GCASH = 'GCASH', 'GCash'
    CARD = 'CARD', 'Card'
    OTHER = 'OTHER', 'Other'


class InvoicePayment(TimeStampedModel):
    """Payment against an invoice."""
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='payments')
    date = models.DateField()
    method = models.CharField(max_length=20, choices=PaymentMethod.choices, default=PaymentMethod.CASH)
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    reference_no = models.CharField(max_length=100, blank=True, default='')
    notes = models.TextField(blank=True, default='')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='invoice_payments_created',
    )

    class Meta:
        ordering = ['-date', '-created_at']

    def __str__(self):
        return f"Payment {self.amount} on INV-{self.invoice.invoice_number}"


class InvoiceLine(models.Model):
    """Invoice line items."""
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='lines')
    item_code = models.CharField(max_length=50)
    item_name = models.CharField(max_length=200)
    qty = models.DecimalField(max_digits=15, decimal_places=4)
    unit = models.CharField(max_length=20)
    unit_price = models.DecimalField(max_digits=15, decimal_places=4)
    discount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    line_total = models.DecimalField(max_digits=15, decimal_places=2)

    def __str__(self):
        return f"{self.item_code} x{self.qty}"


class SupplyCategory(SoftDeleteModel):
    """Category for supplies/raw materials tracked separately."""
    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=30, unique=True)

    class Meta:
        verbose_name_plural = 'Supply categories'
        ordering = ['name']

    def __str__(self):
        return f"[{self.code}] {self.name}"


class SupplyItem(SoftDeleteModel):
    """Supply / raw material item for the supplies inventory tracker."""
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=50, unique=True)
    category = models.ForeignKey(
        SupplyCategory, on_delete=models.PROTECT, related_name='items',
        null=True, blank=True,
    )
    supplier_brand = models.CharField(max_length=200, blank=True, default='', help_text='Supplier or brand name')
    units_per_piece = models.DecimalField(max_digits=15, decimal_places=4, default=1, help_text='How many units per piece/pack')
    unit = models.CharField(max_length=30, default='pcs')
    cost_per_unit = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    current_stock = models.DecimalField(max_digits=15, decimal_places=4, default=0)
    minimum_stock = models.DecimalField(max_digits=15, decimal_places=4, default=0)
    low_stock_alert_level = models.DecimalField(
        max_digits=15, decimal_places=4, default=0,
        help_text='Alert when stock falls to or below this level',
    )
    notes = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f"[{self.code}] {self.name}"

    @property
    def inventory_value(self):
        return self.current_stock * self.cost_per_unit

    @property
    def stock_status(self):
        if self.low_stock_alert_level > 0 and self.current_stock <= self.low_stock_alert_level:
            return 'LOW'
        if self.minimum_stock > 0 and self.current_stock <= self.minimum_stock:
            return 'LOW'
        return 'OK'


class SupplyMovementStatus(models.TextChoices):
    PENDING = 'PENDING', 'Pending'
    COMPLETED = 'COMPLETED', 'Completed'
    CANCELLED = 'CANCELLED', 'Cancelled'


class SupplyMovement(TimeStampedModel):
    """Tracks supply stock-in and usage (stock-out)."""
    MOVEMENT_TYPES = [
        ('IN', 'Stock In'),
        ('OUT', 'Usage / Stock Out'),
    ]
    supply_item = models.ForeignKey(SupplyItem, on_delete=models.PROTECT, related_name='movements')
    movement_type = models.CharField(max_length=3, choices=MOVEMENT_TYPES)
    qty = models.DecimalField(max_digits=15, decimal_places=4)
    unit_cost = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    date = models.DateField()
    status = models.CharField(
        max_length=20, choices=SupplyMovementStatus.choices,
        default=SupplyMovementStatus.COMPLETED,
    )
    notes = models.TextField(blank=True, default='')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='supply_movements_created',
    )

    class Meta:
        ordering = ['-date', '-created_at']

    def __str__(self):
        return f"{self.movement_type} {self.supply_item.code} x{self.qty}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        from django.db.models import Sum, Q, DecimalField as DF
        from django.db.models.functions import Coalesce
        item = self.supply_item
        totals = SupplyMovement.objects.filter(supply_item=item).aggregate(
            total_in=Coalesce(Sum('qty', filter=Q(movement_type='IN')), 0, output_field=DF()),
            total_out=Coalesce(Sum('qty', filter=Q(movement_type='OUT')), 0, output_field=DF()),
        )
        item.current_stock = totals['total_in'] - totals['total_out']
        item.save(update_fields=['current_stock', 'updated_at'])


class TargetGoal(TimeStampedModel):
    """Business targets and goals tracking."""
    PRIORITY_CHOICES = [
        ('HIGH', 'High'),
        ('MEDIUM', 'Medium'),
        ('LOW', 'Low'),
    ]
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('IN_PROGRESS', 'In Progress'),
        ('COMPLETED', 'Completed'),
        ('CANCELLED', 'Cancelled'),
    ]
    title = models.CharField(max_length=300)
    description = models.TextField(blank=True, default='')
    category = models.CharField(max_length=100, blank=True, default='', help_text='e.g. Sales, Expenses, Inventory')
    target_value = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True, help_text='Numeric target (e.g. revenue goal)')
    current_value = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    unit_label = models.CharField(max_length=30, blank=True, default='', help_text='e.g. PHP, units, %')
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='MEDIUM')
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='PENDING')
    due_date = models.DateField(null=True, blank=True)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='assigned_goals',
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='goals_created',
    )

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title

    @property
    def progress_pct(self):
        if self.target_value and self.target_value > 0 and self.current_value is not None:
            return min(round(float(self.current_value) / float(self.target_value) * 100, 1), 100)
        return 0

    @property
    def is_overdue(self):
        from datetime import date
        if self.due_date and self.status not in ('COMPLETED', 'CANCELLED'):
            return self.due_date < date.today()
        return False

    @property
    def days_remaining(self):
        from datetime import date
        if self.due_date:
            delta = (self.due_date - date.today()).days
            return max(delta, 0)
        return 999
