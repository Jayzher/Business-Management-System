from django.contrib import admin
from warehouses.models import Warehouse, Location


class LocationInline(admin.TabularInline):
    model = Location
    extra = 0
    fields = ['code', 'name', 'parent', 'location_type', 'is_pickable', 'is_active']


@admin.register(Warehouse)
class WarehouseAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'city', 'manager', 'allow_negative_stock', 'is_active']
    list_filter = ['is_active', 'city']
    search_fields = ['code', 'name']
    inlines = [LocationInline]


@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'warehouse', 'location_type', 'parent', 'is_pickable', 'is_active']
    list_filter = ['warehouse', 'location_type', 'is_pickable', 'is_active']
    search_fields = ['code', 'name']
