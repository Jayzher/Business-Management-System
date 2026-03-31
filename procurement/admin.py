from django.contrib import admin
from procurement.models import PurchaseOrder, PurchaseOrderLine, GoodsReceipt, GoodsReceiptLine, SupplierCatalogEntry


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
    search_fields = ['document_number', 'supplier__name', 'lines__item__code', 'lines__item__name']
    inlines = [GoodsReceiptLineInline]


@admin.register(SupplierCatalogEntry)
class SupplierCatalogEntryAdmin(admin.ModelAdmin):
    list_display = ['supplier', 'item', 'unit', 'unit_price', 'currency', 'last_po_date', 'last_po_number']
    list_filter = ['supplier', 'currency']
    search_fields = ['supplier__name', 'item__name', 'item__code', 'last_po_number']
