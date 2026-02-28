from django.contrib import admin
from core.models import (
    BusinessProfile, SalesChannel, ExpenseCategory, Expense,
    Invoice, InvoiceLine, SupplyCategory, SupplyItem, SupplyMovement,
    TargetGoal,
)


@admin.register(BusinessProfile)
class BusinessProfileAdmin(admin.ModelAdmin):
    list_display = ('name', 'owner_name', 'phone', 'city', 'currency')


@admin.register(SalesChannel)
class SalesChannelAdmin(admin.ModelAdmin):
    list_display = ('code', 'name')
    search_fields = ('name', 'code')


@admin.register(ExpenseCategory)
class ExpenseCategoryAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'is_cogs')
    list_filter = ('is_cogs',)


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ('date', 'category', 'amount', 'vendor', 'created_by')
    list_filter = ('category', 'date')
    search_fields = ('vendor', 'memo')
    date_hierarchy = 'date'


class InvoiceLineInline(admin.TabularInline):
    model = InvoiceLine
    extra = 0


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ('invoice_number', 'date', 'customer_name', 'grand_total', 'is_paid')
    list_filter = ('is_paid', 'date')
    inlines = [InvoiceLineInline]


@admin.register(SupplyCategory)
class SupplyCategoryAdmin(admin.ModelAdmin):
    list_display = ('code', 'name')


@admin.register(SupplyItem)
class SupplyItemAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'unit', 'current_stock', 'minimum_stock', 'cost_per_unit')
    list_filter = ('category',)


@admin.register(SupplyMovement)
class SupplyMovementAdmin(admin.ModelAdmin):
    list_display = ('date', 'supply_item', 'movement_type', 'qty', 'unit_cost')
    list_filter = ('movement_type', 'date')


@admin.register(TargetGoal)
class TargetGoalAdmin(admin.ModelAdmin):
    list_display = ('title', 'category', 'priority', 'status', 'due_date', 'progress_pct')
    list_filter = ('status', 'priority')
