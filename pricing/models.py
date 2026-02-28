from django.db import models
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
