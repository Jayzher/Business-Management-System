from django.contrib import admin
from django.utils import timezone
from cashflow.models import (
    CashFlowTransaction, CashFlowLog,
    CashFlowStatus, CashFlowLogAction,
)


class CashFlowLogInline(admin.TabularInline):
    model = CashFlowLog
    extra = 0
    readonly_fields = ['action', 'performed_by', 'details', 'old_values', 'new_values', 'created_at']
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.action(description='Approve selected transactions')
def approve_selected(modeladmin, request, queryset):
    pending = queryset.filter(status=CashFlowStatus.PENDING)
    now = timezone.now()
    count = 0
    for txn in pending:
        txn.status = CashFlowStatus.APPROVED
        txn.approved_by = request.user
        txn.approved_at = now
        txn.save(update_fields=['status', 'approved_by', 'approved_at', 'updated_at'])
        CashFlowLog.objects.create(
            transaction=txn,
            action=CashFlowLogAction.APPROVED,
            performed_by=request.user,
            details=f'Bulk-approved via admin.',
        )
        count += 1
    modeladmin.message_user(request, f'{count} transaction(s) approved.')


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
    actions = [approve_selected]


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
