from django.contrib import admin
from mptt.admin import DraggableMPTTAdmin
from catalog.models import Category, Unit, UnitConversion, Item, MaterialSpec, ProductSpec


@admin.register(Category)
class CategoryAdmin(DraggableMPTTAdmin):
    list_display = ['tree_actions', 'indented_title', 'code', 'is_active']
    list_display_links = ['indented_title']
    list_filter = ['is_active']
    search_fields = ['name', 'code']


@admin.register(Unit)
class UnitAdmin(admin.ModelAdmin):
    list_display = ['name', 'abbreviation', 'is_active']
    search_fields = ['name', 'abbreviation']


@admin.register(UnitConversion)
class UnitConversionAdmin(admin.ModelAdmin):
    list_display = ['from_unit', 'to_unit', 'factor']


class MaterialSpecInline(admin.StackedInline):
    model = MaterialSpec
    extra = 0


class ProductSpecInline(admin.StackedInline):
    model = ProductSpec
    extra = 0


@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'item_type', 'category', 'default_unit', 'is_active']
    list_filter = ['item_type', 'category', 'is_active']
    search_fields = ['code', 'name', 'barcode']
    inlines = [MaterialSpecInline, ProductSpecInline]
