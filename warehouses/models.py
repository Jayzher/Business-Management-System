from django.db import models
from core.models import SoftDeleteModel


class Warehouse(SoftDeleteModel):
    """Physical warehouse."""
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=200)
    address = models.TextField(blank=True, default='')
    city = models.CharField(max_length=100, blank=True, default='')
    phone = models.CharField(max_length=30, blank=True, default='')
    manager = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='managed_warehouses'
    )
    allow_negative_stock = models.BooleanField(default=False)

    class Meta:
        ordering = ['code']

    def __str__(self):
        return f"[{self.code}] {self.name}"


class LocationType(models.TextChoices):
    ZONE = 'ZONE', 'Zone'
    AISLE = 'AISLE', 'Aisle'
    RACK = 'RACK', 'Rack'
    BIN = 'BIN', 'Bin'


class Location(SoftDeleteModel):
    """Hierarchical storage location within a warehouse."""
    warehouse = models.ForeignKey(Warehouse, on_delete=models.CASCADE, related_name='locations')
    code = models.CharField(max_length=50, db_index=True)
    name = models.CharField(max_length=200)
    parent = models.ForeignKey(
        'self', on_delete=models.CASCADE, null=True, blank=True, related_name='children'
    )
    location_type = models.CharField(
        max_length=20, choices=LocationType.choices, default=LocationType.BIN
    )
    is_pickable = models.BooleanField(default=True)

    class Meta:
        unique_together = ('warehouse', 'code')
        ordering = ['warehouse', 'code']

    def __str__(self):
        return f"{self.warehouse.code}-{self.code}"

    @property
    def full_path(self):
        parts = [self.code]
        parent = self.parent
        while parent:
            parts.insert(0, parent.code)
            parent = parent.parent
        return ' > '.join(parts)
