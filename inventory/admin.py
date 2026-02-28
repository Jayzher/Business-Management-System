from django.contrib import admin
from inventory.models import (
    StockMove, StockBalance, StockReservation,
    StockAdjustment, StockAdjustmentLine,
    DamagedReport, DamagedReportLine,
    StockTransfer, StockTransferLine,
)


@admin.register(StockMove)
class StockMoveAdmin(admin.ModelAdmin):
    list_display = ['id', 'move_type', 'item', 'qty', 'unit', 'from_location', 'to_location', 'status', 'reference_number', 'posted_at']
    list_filter = ['move_type', 'status']
    search_fields = ['item__code', 'item__name', 'reference_number']
    readonly_fields = ['created_at', 'posted_at']


@admin.register(StockBalance)
class StockBalanceAdmin(admin.ModelAdmin):
    list_display = ['item', 'location', 'qty_on_hand', 'qty_reserved', 'updated_at']
    list_filter = ['location__warehouse']
    search_fields = ['item__code', 'item__name']


@admin.register(StockReservation)
class StockReservationAdmin(admin.ModelAdmin):
    list_display = ['item', 'location', 'qty', 'reference_type', 'reference_id', 'is_fulfilled']
    list_filter = ['is_fulfilled']


class StockAdjustmentLineInline(admin.TabularInline):
    model = StockAdjustmentLine
    extra = 1


@admin.register(StockAdjustment)
class StockAdjustmentAdmin(admin.ModelAdmin):
    list_display = ['document_number', 'warehouse', 'reason', 'status', 'created_by', 'created_at']
    list_filter = ['status', 'warehouse']
    search_fields = ['document_number']
    inlines = [StockAdjustmentLineInline]


class DamagedReportLineInline(admin.TabularInline):
    model = DamagedReportLine
    extra = 1


@admin.register(DamagedReport)
class DamagedReportAdmin(admin.ModelAdmin):
    list_display = ['document_number', 'warehouse', 'status', 'created_by', 'created_at']
    list_filter = ['status', 'warehouse']
    search_fields = ['document_number']
    inlines = [DamagedReportLineInline]


class StockTransferLineInline(admin.TabularInline):
    model = StockTransferLine
    extra = 1


@admin.register(StockTransfer)
class StockTransferAdmin(admin.ModelAdmin):
    list_display = ['document_number', 'from_warehouse', 'to_warehouse', 'status', 'created_by', 'created_at']
    list_filter = ['status', 'from_warehouse', 'to_warehouse']
    search_fields = ['document_number']
    inlines = [StockTransferLineInline]


@admin.register(StockTransferLine)
class StockTransferLineAdmin(admin.ModelAdmin):
    list_display = ['transfer', 'item', 'from_location', 'to_location', 'qty', 'unit']
    list_filter = ['from_location__warehouse', 'to_location__warehouse']
    search_fields = ['transfer__document_number', 'item__code', 'item__name']
