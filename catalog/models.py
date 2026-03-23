from decimal import Decimal
from django.core.exceptions import ValidationError
from django.db import models
from mptt.models import MPTTModel, TreeForeignKey
from core.models import SoftDeleteModel


class UnitCategory(models.TextChoices):
    QUANTITY = 'quantity', 'Quantity'
    LENGTH = 'length', 'Length'
    MASS = 'mass', 'Mass'
    VOLUME = 'volume', 'Volume'
    AREA = 'area', 'Area'
    MATERIAL = 'material', 'Material'
    LOGISTICS = 'logistics', 'Logistics'


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
    category = models.CharField(
        max_length=20,
        choices=UnitCategory.choices,
        default=UnitCategory.QUANTITY,
        db_index=True,
        help_text='Measurement category — conversions are only allowed within the same category.',
    )

    class Meta:
        ordering = ['category', 'name']

    def __str__(self):
        return f"{self.name} ({self.abbreviation})"


class UnitConversion(SoftDeleteModel):
    """Conversion factor between units (e.g., 1 box = 20 pcs).
    Both units must share the same category.
    Optionally scoped to a specific Item — item-specific records take precedence
    over global ones when item is provided to convert_to_base_unit()."""
    from_unit = models.ForeignKey(Unit, on_delete=models.CASCADE, related_name='conversions_from')
    to_unit = models.ForeignKey(Unit, on_delete=models.CASCADE, related_name='conversions_to')
    factor = models.DecimalField(max_digits=15, decimal_places=6)
    conversion_price = models.DecimalField(
        max_digits=15, decimal_places=4, null=True, blank=True,
        help_text='Explicit selling price per 1 to_unit when using this conversion. '
                  'If set, overrides the factor-based price calculation for selling price lookups. '
                  'COGS always uses cost_price regardless of this field. '
                  'Example: Roll→ft with factor=5 and conversion_price=30 means each ft sells for 30.',
    )
    item = models.ForeignKey(
        'catalog.Item',
        on_delete=models.CASCADE,
        null=True, blank=True,
        related_name='unit_conversions',
        help_text='Leave blank for a global conversion. Set to override the factor for a specific product.',
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['from_unit', 'to_unit'],
                condition=models.Q(item__isnull=True),
                name='unique_unit_conv_global',
            ),
            models.UniqueConstraint(
                fields=['from_unit', 'to_unit', 'item'],
                condition=models.Q(item__isnull=False),
                name='unique_unit_conv_per_item',
            ),
        ]

    def clean(self):
        if self.from_unit_id and self.to_unit_id:
            if self.from_unit_id == self.to_unit_id:
                raise ValidationError('A unit cannot be converted to itself.')

    def __str__(self):
        scope = f' [{self.item.code}]' if self.item_id else ''
        return f"1 {self.from_unit.abbreviation} = {self.factor} {self.to_unit.abbreviation}{scope}"


def convert_to_base_unit(qty, sale_unit, base_unit, item=None):
    """Convert *qty* expressed in *sale_unit* to *base_unit* for inventory.

    Rules:
    - If sale_unit == base_unit, return qty unchanged.
    - When *item* is supplied, item-specific UnitConversion records are
      checked first before falling back to global (item=NULL) ones.
    - Looks up a UnitConversion (direct or reverse), even across categories.
      Raises ValueError only when no applicable conversion exists.
    """
    if sale_unit.pk == base_unit.pk:
        return qty

    def _lookup(from_u, to_u):
        """Return (conv, is_reverse) or (None, False). Item-specific first."""
        if item is not None:
            c = UnitConversion.objects.filter(
                from_unit=from_u, to_unit=to_u, item=item, is_active=True
            ).first()
            if c:
                return c, False
        c = UnitConversion.objects.filter(
            from_unit=from_u, to_unit=to_u, item__isnull=True, is_active=True
        ).first()
        return c, False

    # Try direct: sale_unit → base_unit
    conv, _ = _lookup(sale_unit, base_unit)
    if conv:
        return qty * conv.factor

    # Try reverse: base_unit → sale_unit, then divide by factor
    conv, _ = _lookup(base_unit, sale_unit)
    if conv:
        if conv.factor == 0:
            raise ValueError(
                f'Invalid unit conversion configured between {sale_unit} and {base_unit}: factor cannot be zero.'
            )
        return qty / conv.factor

    raise ValueError(
        f'No unit conversion configured between {sale_unit} and {base_unit}'
        + (f' for item {item.code}' if item is not None and getattr(item, 'code', None) else '')
        + '. Please add one under Catalog → Unit Conversions.'
    )


class ItemType(models.TextChoices):
    RAW = 'RAW', 'Raw Material'
    FINISHED = 'FINISHED', 'Finished Product'
    SERVICE = 'SERVICE', 'Service'


class Item(SoftDeleteModel):
    """Base item model for both raw materials and finished products."""
    code = models.CharField(max_length=50, unique=True, db_index=True)
    name = models.CharField(max_length=200)
    item_type = models.CharField(
        max_length=20, choices=ItemType.choices, db_index=True,
        default=ItemType.RAW,
    )
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name='items')
    default_unit = models.ForeignKey(Unit, on_delete=models.PROTECT, related_name='items')
    selling_unit = models.ForeignKey(
        Unit, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='selling_items',
        help_text='Default unit used when selling this item. Falls back to the base unit when not set.',
    )
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

    @property
    def stock_unit(self):
        """The canonical unit for all inventory storage (StockBalance/StockMove).

        Returns selling_unit when explicitly set, otherwise falls back to
        default_unit.  All posting services must convert to this unit before
        writing to StockBalance so that every quantity is normalised to the
        selling/inventory unit regardless of the procurement unit used.
        """
        return self.selling_unit if self.selling_unit_id else self.default_unit

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
