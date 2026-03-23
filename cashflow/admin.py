from django.contrib import admin
from cashflow.models import CashFlowTransaction, CashFlowLog


class CashFlowLogInline(admin.TabularInline):
    model = CashFlowLog
    extra = 0
    readonly_fields = ['action', 'performed_by', 'details', 'old_values', 'new_values', 'created_at']
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(CashFlowTransaction)
class CashFlowTransactionAdmin(admin.ModelAdmin):
    list_display = [
        'transaction_number', 'category', 'flow_type', 'amount',
        'transaction_date', 'payment_method', 'status', 'created_by',
    ]
    list_filter = ['category', 'flow_type', 'status', 'payment_method', 'transaction_date']
    search_fields = ['transaction_number', 'reason', 'reference_no', 'notes']
    readonly_fields = ['transaction_number', 'created_by', 'approved_by', 'approved_at', 'rejected_by', 'rejected_at']
    date_hierarchy = 'transaction_date'
    inlines = [CashFlowLogInline]


@admin.register(CashFlowLog)
class CashFlowLogAdmin(admin.ModelAdmin):
    list_display = ['transaction', 'action', 'performed_by', 'created_at']
    list_filter = ['action']
    search_fields = ['transaction__transaction_number', 'details']
    readonly_fields = ['transaction', 'action', 'performed_by', 'details', 'old_values', 'new_values']

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
