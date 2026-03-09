from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from core.models import SoftDeleteModel


class PriceList(SoftDeleteModel):
    """Price list header — can be warehouse-specific or global."""
    name = models.CharField(max_length=200)
    warehouse = models.ForeignKey(
        'warehouses.Warehouse', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='price_lists',
    )
    currency = models.CharField(max_length=10, default='PHP')
    is_default = models.BooleanField(default=False)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class PriceListItem(SoftDeleteModel):
    """Price for a specific item/unit within a price list."""
    price_list = models.ForeignKey(PriceList, on_delete=models.CASCADE, related_name='items')
    item = models.ForeignKey('catalog.Item', on_delete=models.PROTECT, related_name='price_list_items')
    unit = models.ForeignKey('catalog.Unit', on_delete=models.PROTECT)
    price = models.DecimalField(max_digits=15, decimal_places=4)
    min_qty = models.DecimalField(max_digits=15, decimal_places=4, default=1)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)

    class Meta:
        unique_together = ('price_list', 'item', 'unit', 'min_qty', 'start_date')
        ordering = ['price_list', 'item', 'min_qty']

    def __str__(self):
        return f"{self.item.code} @ {self.price} ({self.price_list.name})"


class CustomerPriceCatalog(SoftDeleteModel):
    """
    A custom pricing catalog tied to a specific customer.
    When a Sales Order is created for this customer, item prices from this
    catalog override the default catalog selling_price for matching items.
    """
    customer = models.ForeignKey(
        'partners.Customer', on_delete=models.CASCADE,
        related_name='price_catalogs',
    )
    name = models.CharField(max_length=200, help_text='Descriptive name, e.g. "VIP Wholesale Pricing".')
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['customer__name', 'name', 'start_date']

    def clean(self):
        super().clean()
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValidationError({'end_date': 'End date must be on or after the start date.'})

        overlap_qs = CustomerPriceCatalog.objects.filter(
            customer=self.customer,
            is_active=True,
        )
        if self.pk:
            overlap_qs = overlap_qs.exclude(pk=self.pk)

        new_start = self.start_date
        new_end = self.end_date

        if new_start is not None:
            overlap_qs = overlap_qs.filter(Q(end_date__isnull=True) | Q(end_date__gte=new_start))

        if new_end is not None:
            overlap_qs = overlap_qs.filter(Q(start_date__isnull=True) | Q(start_date__lte=new_end))

        overlapping = overlap_qs.select_related('customer').first()
        if overlapping:
            overlap_start = overlapping.start_date.isoformat() if overlapping.start_date else 'no start'
            overlap_end = overlapping.end_date.isoformat() if overlapping.end_date else 'no end'
            raise ValidationError(
                f'Another active customer pricing catalog for {self.customer.name} overlaps this date range: '
                f'{overlapping.name} ({overlap_start} to {overlap_end}).'
            )

    def __str__(self):
        return f"{self.customer.name} – {self.name}"


class CustomerPriceCatalogItem(models.Model):
    """One item entry inside a customer's price catalog."""
    catalog = models.ForeignKey(
        CustomerPriceCatalog, on_delete=models.CASCADE, related_name='items',
    )
    item = models.ForeignKey('catalog.Item', on_delete=models.PROTECT, related_name='customer_prices')
    unit = models.ForeignKey('catalog.Unit', on_delete=models.PROTECT)
    price = models.DecimalField(max_digits=15, decimal_places=4)
    notes = models.CharField(max_length=200, blank=True, default='')

    class Meta:
        unique_together = ('catalog', 'item', 'unit')
        ordering = ['item__code']

    def __str__(self):
        return f"{self.item.code} @ {self.price}"


class DiscountType(models.TextChoices):
    PERCENT = 'PERCENT', 'Percentage'
    FIXED = 'FIXED', 'Fixed Amount'


class DiscountScope(models.TextChoices):
    ITEM = 'ITEM', 'Per Item'
    ORDER = 'ORDER', 'Per Order'


class DiscountRule(SoftDeleteModel):
    """Simple discount rules."""
    name = models.CharField(max_length=200)
    discount_type = models.CharField(max_length=10, choices=DiscountType.choices)
    value = models.DecimalField(max_digits=15, decimal_places=4)
    scope = models.CharField(max_length=10, choices=DiscountScope.choices, default=DiscountScope.ORDER)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.discount_type} {self.value})"
