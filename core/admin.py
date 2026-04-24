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
    list_display = ('invoice_number', 'date', 'customer_name', 'grand_total', 'delivery_charge', 'is_paid')
    list_filter = ('is_paid', 'date', 'invoice_number')
    search_fields = ('invoice_number', 'customer_name')
    inlines = [InvoiceLineInline]
    fields = (
        'invoice_number', 'date', 'due_date',
        'pos_sale', 'sales_order',
        'customer_name', 'customer_address', 'customer_tin',
        'subtotal', 'discount_total', 'tax_total', 'delivery_charge', 'grand_total',
        'grand_total_cogs', 'notes',
        'is_paid', 'paid_at', 'paid_date',
        'is_void', 'void_reason',
        'created_by',
    )
    readonly_fields = ('created_by',)


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
