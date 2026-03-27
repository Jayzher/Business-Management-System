from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.db.models import Sum, Q, DecimalField
from django.db.models.functions import Coalesce

from cashflow.models import (
    CashFlowTransaction, CashFlowLog, CashFlowLogAction,
    CashFlowStatus, CashFlowType,
)
from cashflow.forms import CashFlowTransactionForm, CashFlowRejectForm


def _log(transaction, action, user, details='', old_values=None, new_values=None):
    """Create an audit log entry."""
    CashFlowLog.objects.create(
        transaction=transaction,
        action=action,
        performed_by=user,
        details=details,
        old_values=old_values,
        new_values=new_values,
    )


# ═══════════════════════════════════════════════════════════════════════════
# TRANSACTION LIST
# ═══════════════════════════════════════════════════════════════════════════
@login_required
def transaction_list(request):
    qs = CashFlowTransaction.objects.select_related('created_by', 'approved_by').all()

    # Filters
    category = request.GET.get('category', '')
    flow_type = request.GET.get('flow_type', '')
    status = request.GET.get('status', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')

    if category:
        qs = qs.filter(category=category)
    if flow_type:
        qs = qs.filter(flow_type=flow_type)
    if status:
        qs = qs.filter(status=status)
    if date_from:
        qs = qs.filter(transaction_date__gte=date_from)
    if date_to:
        qs = qs.filter(transaction_date__lte=date_to)

    # Summary totals
    totals = qs.aggregate(
        total_in=Coalesce(
            Sum('amount', filter=Q(flow_type=CashFlowType.CASH_IN)),
            0, output_field=DecimalField(),
        ),
        total_out=Coalesce(
            Sum('amount', filter=Q(flow_type=CashFlowType.CASH_OUT)),
            0, output_field=DecimalField(),
        ),
    )

    return render(request, 'cashflow/transaction_list.html', {
        'transactions': qs,
        'filters': {
            'category': category,
            'flow_type': flow_type,
            'status': status,
            'date_from': date_from,
            'date_to': date_to,
        },
        'total_in': totals['total_in'],
        'total_out': totals['total_out'],
        'net': totals['total_in'] - totals['total_out'],
        'category_choices': CashFlowTransaction._meta.get_field('category').choices,
        'flow_type_choices': CashFlowTransaction._meta.get_field('flow_type').choices,
        'status_choices': CashFlowTransaction._meta.get_field('status').choices,
    })


# ═══════════════════════════════════════════════════════════════════════════
# TRANSACTION DETAIL
# ═══════════════════════════════════════════════════════════════════════════
@login_required
def transaction_detail(request, pk):
    txn = get_object_or_404(
        CashFlowTransaction.objects.select_related(
            'created_by', 'approved_by', 'rejected_by',
        ),
        pk=pk,
    )
    logs = txn.logs.select_related('performed_by').all()
    reject_form = CashFlowRejectForm()
    return render(request, 'cashflow/transaction_detail.html', {
        'txn': txn,
        'logs': logs,
        'reject_form': reject_form,
    })


# ═══════════════════════════════════════════════════════════════════════════
# TRANSACTION CREATE
# ═══════════════════════════════════════════════════════════════════════════
@login_required
def transaction_create(request):
    if request.method == 'POST':
        form = CashFlowTransactionForm(request.POST)
        if form.is_valid():
            txn = form.save(commit=False)
            txn.transaction_number = CashFlowTransaction.generate_next_number()
            txn.created_by = request.user
            txn.status = CashFlowStatus.PENDING
            txn.save()
            _log(txn, CashFlowLogAction.CREATED, request.user,
                 f'Transaction {txn.transaction_number} created.')
            messages.success(request, f'Transaction {txn.transaction_number} created.')
            return redirect('cashflow_list')
    else:
        form = CashFlowTransactionForm()
    return render(request, 'cashflow/transaction_form.html', {
        'form': form, 'title': 'New Cash Flow Transaction',
    })


# ═══════════════════════════════════════════════════════════════════════════
# TRANSACTION EDIT
# ═══════════════════════════════════════════════════════════════════════════
@login_required
def transaction_edit(request, pk):
    txn = get_object_or_404(CashFlowTransaction, pk=pk)
    if txn.status not in (CashFlowStatus.PENDING, CashFlowStatus.REJECTED):
        messages.warning(request, 'Only Pending or Rejected transactions can be edited.')
        return redirect('cashflow_detail', pk=pk)

    old_data = {
        'category': txn.category, 'flow_type': txn.flow_type,
        'amount': str(txn.amount), 'transaction_date': str(txn.transaction_date),
        'payment_method': txn.payment_method, 'reason': txn.reason,
    }

    if request.method == 'POST':
        form = CashFlowTransactionForm(request.POST, instance=txn)
        if form.is_valid():
            txn = form.save(commit=False)
            # If rejected, move back to pending on edit
            if txn.status == CashFlowStatus.REJECTED:
                txn.status = CashFlowStatus.PENDING
            txn.save()
            new_data = {
                'category': txn.category, 'flow_type': txn.flow_type,
                'amount': str(txn.amount), 'transaction_date': str(txn.transaction_date),
                'payment_method': txn.payment_method, 'reason': txn.reason,
            }
            _log(txn, CashFlowLogAction.UPDATED, request.user,
                 f'Transaction {txn.transaction_number} updated.',
                 old_values=old_data, new_values=new_data)
            messages.success(request, f'Transaction {txn.transaction_number} updated.')
            return redirect('cashflow_list')
    else:
        form = CashFlowTransactionForm(instance=txn)
    return render(request, 'cashflow/transaction_form.html', {
        'form': form, 'title': f'Edit: {txn.transaction_number}',
    })


# ═══════════════════════════════════════════════════════════════════════════
# TRANSACTION DELETE
# ═══════════════════════════════════════════════════════════════════════════
@login_required
def transaction_delete(request, pk):
    txn = get_object_or_404(CashFlowTransaction, pk=pk)
    if txn.status == CashFlowStatus.APPROVED:
        messages.warning(request, 'Approved transactions cannot be deleted.')
        return redirect('cashflow_detail', pk=pk)

    if request.method == 'POST':
        _log(txn, CashFlowLogAction.DELETED, request.user,
             f'Transaction {txn.transaction_number} deleted.')
        txn.soft_delete()
        messages.success(request, f'Transaction {txn.transaction_number} deleted.')
        return redirect('cashflow_list')
    return render(request, 'cashflow/transaction_delete.html', {'object': txn})


# ═══════════════════════════════════════════════════════════════════════════
# APPROVE / REJECT / CANCEL
# ═══════════════════════════════════════════════════════════════════════════
@login_required
def transaction_approve(request, pk):
    txn = get_object_or_404(CashFlowTransaction, pk=pk)
    if request.method != 'POST':
        return redirect('cashflow_detail', pk=pk)
    if txn.status != CashFlowStatus.PENDING:
        messages.warning(request, 'Only Pending transactions can be approved.')
        return redirect('cashflow_detail', pk=pk)

    txn.status = CashFlowStatus.APPROVED
    txn.approved_by = request.user
    txn.approved_at = timezone.now()
    txn.save(update_fields=['status', 'approved_by', 'approved_at', 'updated_at'])
    _log(txn, CashFlowLogAction.APPROVED, request.user,
         f'Transaction {txn.transaction_number} approved.')
    messages.success(request, f'Transaction {txn.transaction_number} approved.')
    return redirect('cashflow_detail', pk=pk)


@login_required
def transaction_reject(request, pk):
    txn = get_object_or_404(CashFlowTransaction, pk=pk)
    if request.method != 'POST':
        return redirect('cashflow_detail', pk=pk)
    if txn.status != CashFlowStatus.PENDING:
        messages.warning(request, 'Only Pending transactions can be rejected.')
        return redirect('cashflow_detail', pk=pk)

    form = CashFlowRejectForm(request.POST)
    reason = ''
    if form.is_valid():
        reason = form.cleaned_data['rejection_reason']

    txn.status = CashFlowStatus.REJECTED
    txn.rejected_by = request.user
    txn.rejected_at = timezone.now()
    txn.rejection_reason = reason
    txn.save(update_fields=[
        'status', 'rejected_by', 'rejected_at', 'rejection_reason', 'updated_at',
    ])
    _log(txn, CashFlowLogAction.REJECTED, request.user,
         f'Transaction {txn.transaction_number} rejected. Reason: {reason}')
    messages.success(request, f'Transaction {txn.transaction_number} rejected.')
    return redirect('cashflow_detail', pk=pk)


@login_required
def transaction_cancel(request, pk):
    txn = get_object_or_404(CashFlowTransaction, pk=pk)
    if request.method != 'POST':
        return redirect('cashflow_detail', pk=pk)
    if txn.status == CashFlowStatus.CANCELLED:
        messages.warning(request, 'Transaction is already cancelled.')
        return redirect('cashflow_detail', pk=pk)

    old_status = txn.status
    txn.status = CashFlowStatus.CANCELLED
    txn.save(update_fields=['status', 'updated_at'])
    _log(txn, CashFlowLogAction.CANCELLED, request.user,
         f'Transaction {txn.transaction_number} cancelled (was {old_status}).')
    messages.success(request, f'Transaction {txn.transaction_number} cancelled.')
    return redirect('cashflow_detail', pk=pk)


# ═══════════════════════════════════════════════════════════════════════════
# CASH FLOW LOGS
# ═══════════════════════════════════════════════════════════════════════════
@login_required
def log_list(request):
    qs = (
        CashFlowLog.objects
        .select_related('transaction', 'performed_by')
        .all()[:500]
    )
    return render(request, 'cashflow/log_list.html', {'logs': qs})


# ═══════════════════════════════════════════════════════════════════════════
# SYNC — Weekly sales gross-profit recalculation
# ═══════════════════════════════════════════════════════════════════════════
@login_required
def sync_cashflow(request):
    """
    POST-only view.  Deletes all auto-generated WeeklySalesRevenue entries
    and rebuilds them by calculating (Revenue - COGS) per ISO week across
    all posted POS, Delivery Note, Sales Pickup and Sales Return documents.
    """
    if request.method != 'POST':
        return redirect('cashflow_list')

    from cashflow.sync import sync_weekly_sales_revenue
    try:
        count = sync_weekly_sales_revenue(request.user)
        messages.success(
            request,
            f'Cash flow sync complete — {count} weekly sales entr'
            f'{"y" if count == 1 else "ies"} created.',
        )
    except Exception as exc:
        messages.error(request, f'Sync failed: {exc}')

    return redirect('cashflow_list')
