from django.db import models
from mptt.models import MPTTModel, TreeForeignKey
from core.models import SoftDeleteModel


class Category(MPTTModel, SoftDeleteModel):
    """Hierarchical category tree (Raw Materials > Aluminum > Profiles, etc.)."""
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=30, unique=True)
    parent = TreeForeignKey(
        'self', on_delete=models.CASCADE, null=True, blank=True, related_name='children'
    )
    description = models.TextField(blank=True, default='')

    class MPTTMeta:
        order_insertion_by = ['name']

    class Meta:
        verbose_name_plural = 'categories'

    def __str__(self):
        return self.name


class Unit(SoftDeleteModel):
    """Unit of measure (pcs, m, kg, sheet, bar, box)."""
    name = models.CharField(max_length=50, unique=True)
    abbreviation = models.CharField(max_length=10, unique=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.abbreviation})"


class UnitConversion(SoftDeleteModel):
    """Conversion factor between units (e.g., 1 box = 20 pcs)."""
    from_unit = models.ForeignKey(Unit, on_delete=models.CASCADE, related_name='conversions_from')
    to_unit = models.ForeignKey(Unit, on_delete=models.CASCADE, related_name='conversions_to')
    factor = models.DecimalField(max_digits=15, decimal_places=6)

    class Meta:
        unique_together = ('from_unit', 'to_unit')

    def __str__(self):
        return f"1 {self.from_unit.abbreviation} = {self.factor} {self.to_unit.abbreviation}"


class ItemType(models.TextChoices):
    RAW = 'RAW', 'Raw Material'
    FINISHED = 'FINISHED', 'Finished Product'
    SERVICE = 'SERVICE', 'Service'


class Item(SoftDeleteModel):
    """Base item model for both raw materials and finished products."""
    code = models.CharField(max_length=50, unique=True, db_index=True)
    name = models.CharField(max_length=200)
    item_type = models.CharField(max_length=20, choices=ItemType.choices, db_index=True)
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name='items')
    default_unit = models.ForeignKey(Unit, on_delete=models.PROTECT, related_name='items')
    description = models.TextField(blank=True, default='')
    barcode = models.CharField(max_length=100, blank=True, default='', db_index=True)
    minimum_stock = models.DecimalField(max_digits=15, decimal_places=4, default=0)
    maximum_stock = models.DecimalField(max_digits=15, decimal_places=4, default=0)
    reorder_point = models.DecimalField(max_digits=15, decimal_places=4, default=0)
    cost_price = models.DecimalField(
        max_digits=15, decimal_places=4, default=0,
        help_text='Weighted average cost used for COGS and profit margin calculations.',
    )
    selling_price = models.DecimalField(
        max_digits=15, decimal_places=4, default=0,
        help_text='Default selling price. Overridden by Price Lists when assigned.',
    )
    image = models.ImageField(upload_to='items/', blank=True, null=True)

    class Meta:
        ordering = ['code']

    def __str__(self):
        return f"[{self.code}] {self.name}"


class MaterialSpec(SoftDeleteModel):
    """Extended specs for raw materials (aluminum profiles, glass, etc.)."""
    item = models.OneToOneField(Item, on_delete=models.CASCADE, related_name='material_spec')
    thickness = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    length = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    width = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    color = models.CharField(max_length=50, blank=True, default='')
    alloy = models.CharField(max_length=50, blank=True, default='')
    grade = models.CharField(max_length=50, blank=True, default='')

    def __str__(self):
        return f"Spec: {self.item.code}"


class ProductSpec(SoftDeleteModel):
    """Extended specs for finished products."""
    item = models.OneToOneField(Item, on_delete=models.CASCADE, related_name='product_spec')
    model_name = models.CharField(max_length=100, blank=True, default='')
    variant = models.CharField(max_length=100, blank=True, default='')
    dimensions = models.CharField(max_length=100, blank=True, default='')
    weight = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)

    def __str__(self):
        return f"Spec: {self.item.code}"
