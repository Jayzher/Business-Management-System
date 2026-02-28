from django.contrib import admin
from pricing.models import PriceList, PriceListItem, DiscountRule


class PriceListItemInline(admin.TabularInline):
    model = PriceListItem
    extra = 1


@admin.register(PriceList)
class PriceListAdmin(admin.ModelAdmin):
    list_display = ['name', 'warehouse', 'currency', 'is_default', 'is_active']
    list_filter = ['is_default', 'is_active']
    inlines = [PriceListItemInline]


@admin.register(PriceListItem)
class PriceListItemAdmin(admin.ModelAdmin):
    list_display = ['price_list', 'item', 'unit', 'price', 'min_qty', 'start_date', 'end_date']
    list_filter = ['price_list']


@admin.register(DiscountRule)
class DiscountRuleAdmin(admin.ModelAdmin):
    list_display = ['name', 'discount_type', 'value', 'scope', 'is_active']
    list_filter = ['discount_type', 'scope', 'is_active']
