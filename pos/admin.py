from django.contrib import admin
from pos.models import (
    POSRegister, POSShift, POSSale, POSSaleLine,
    POSPayment, POSRefund, POSRefundLine, CashEntry,
)


class POSSaleLineInline(admin.TabularInline):
    model = POSSaleLine
    extra = 0


class POSPaymentInline(admin.TabularInline):
    model = POSPayment
    extra = 0


class POSRefundLineInline(admin.TabularInline):
    model = POSRefundLine
    extra = 0


@admin.register(POSRegister)
class POSRegisterAdmin(admin.ModelAdmin):
    list_display = ['name', 'warehouse', 'default_location', 'price_list', 'is_active']
    list_filter = ['warehouse', 'is_active']


@admin.register(POSShift)
class POSShiftAdmin(admin.ModelAdmin):
    list_display = ['id', 'register', 'opened_by', 'opened_at', 'status', 'opening_cash']
    list_filter = ['status', 'register']


@admin.register(POSSale)
class POSSaleAdmin(admin.ModelAdmin):
    list_display = ['sale_no', 'register', 'status', 'grand_total', 'created_by', 'created_at']
    list_filter = ['status', 'register']
    search_fields = ['sale_no']
    inlines = [POSSaleLineInline, POSPaymentInline]


@admin.register(POSRefund)
class POSRefundAdmin(admin.ModelAdmin):
    list_display = ['refund_no', 'original_sale', 'status', 'grand_total', 'created_by']
    list_filter = ['status']
    inlines = [POSRefundLineInline]


@admin.register(CashEntry)
class CashEntryAdmin(admin.ModelAdmin):
    list_display = ['shift', 'entry_type', 'amount', 'reason', 'created_by', 'created_at']
    list_filter = ['entry_type']
