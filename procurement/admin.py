from django.contrib import admin
from procurement.models import PurchaseOrder, PurchaseOrderLine, GoodsReceipt, GoodsReceiptLine


class PurchaseOrderLineInline(admin.TabularInline):
    model = PurchaseOrderLine
    extra = 1


@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(admin.ModelAdmin):
    list_display = ['document_number', 'supplier', 'warehouse', 'order_date', 'status', 'created_by']
    list_filter = ['status', 'supplier', 'warehouse']
    search_fields = ['document_number', 'supplier__name']
    inlines = [PurchaseOrderLineInline]


class GoodsReceiptLineInline(admin.TabularInline):
    model = GoodsReceiptLine
    extra = 1


@admin.register(GoodsReceipt)
class GoodsReceiptAdmin(admin.ModelAdmin):
    list_display = ['document_number', 'purchase_order', 'supplier', 'warehouse', 'receipt_date', 'status', 'created_by']
    list_filter = ['status', 'supplier', 'warehouse']
    search_fields = ['document_number', 'supplier__name']
    inlines = [GoodsReceiptLineInline]
