from django.contrib import admin
from sales.models import SalesOrder, SalesOrderLine, DeliveryNote, DeliveryLine


class SalesOrderLineInline(admin.TabularInline):
    model = SalesOrderLine
    extra = 1


@admin.register(SalesOrder)
class SalesOrderAdmin(admin.ModelAdmin):
    list_display = ['document_number', 'customer', 'warehouse', 'order_date', 'delivery_date', 'status', 'created_by']
    list_filter = ['status', 'customer', 'warehouse']
    search_fields = ['document_number', 'customer__name']
    inlines = [SalesOrderLineInline]


class DeliveryLineInline(admin.TabularInline):
    model = DeliveryLine
    extra = 1


@admin.register(DeliveryNote)
class DeliveryNoteAdmin(admin.ModelAdmin):
    list_display = ['document_number', 'sales_order', 'customer', 'warehouse', 'delivery_date', 'status', 'created_by']
    list_filter = ['status', 'customer', 'warehouse']
    search_fields = ['document_number', 'customer__name']
    inlines = [DeliveryLineInline]
