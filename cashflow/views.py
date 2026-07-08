from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.http import JsonResponse
from django.db.models import Sum, Q, DecimalField
from django.db.models.functions import Coalesce

from cashflow.models import (
    CashFlowTransaction, CashFlowLog, CashFlowLogAction,
    CashFlowStatus, CashFlowType, CashFlowCategory,
)
from cashflow.forms import CashFlowTransactionForm, CashFlowRejectForm
from accounts.decorators import write_denied_for_viewer


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
# TRANSACTION LIST - MONTHLY VIEW
# ═══════════════════════════════════════════════════════════════════════════
@login_required
def transaction_list(request):
    """Monthly cashflow view with comprehensive breakdown, pagination, filters, and search."""
    from datetime import date, datetime
    from decimal import Decimal
    from calendar import month_name
    from cashflow.monthly_signals import update_monthly_summary
    from cashflow.models import MonthlyCashflowSummary
    from pos.models import POSSale, SaleStatus
    from core.models import Invoice, Expense
    from procurement.models import GoodsReceipt
    from core.models import DocumentStatus
    from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
    from django.db.models import Q
    
    # Get current month or requested month
    today = date.today()
    year = int(request.GET.get('year', today.year))
    month = int(request.GET.get('month', today.month))
    
    # Ensure valid month
    if month < 1 or month > 12:
        month = today.month
    
    # Get or create monthly summary
    try:
        summary = MonthlyCashflowSummary.objects.get(year=year, month=month)
    except MonthlyCashflowSummary.DoesNotExist:
        summary = update_monthly_summary(year, month, user=request.user)
    
    # Date range for this month
    if month == 12:
        next_month = date(year + 1, 1, 1)
    else:
        next_month = date(year, month + 1, 1)
    start_date = date(year, month, 1)
    end_date = next_month
    # Timezone-aware bounds for POSSale.posted_at — must match the field used
    # by cashflow.monthly_signals so this page's breakdown always agrees
    # with the summary card totals shown alongside it.
    start_dt = timezone.make_aware(datetime.combine(start_date, datetime.min.time()))
    end_dt = timezone.make_aware(datetime.combine(end_date, datetime.min.time()))
    
    # ── Filters & Search ─────────────────────────────────────────────────
    search_query = request.GET.get('search', '').strip()
    filter_type = request.GET.get('filter_type', 'all')  # all, sales, cash_in, procurement, expenses, cash_out
    per_page = int(request.GET.get('per_page', 20))
    
    # Get detailed breakdown
    # Capital - Sales
    from core.cogs import pos_sale_cogs
    
    pos_sales_qs = POSSale.objects.filter(
        status=SaleStatus.POSTED,
        posted_at__gte=start_dt,
        posted_at__lt=end_dt,
    ).select_related('created_by').prefetch_related('lines__item', 'lines__unit', 'bundle_lines__price_list__items')
    
    invoices_qs = Invoice.objects.filter(
        is_void=False,
        date__gte=start_date,
        date__lt=end_date,
        pos_sale__isnull=True,
    ).select_related('created_by')
    
    # Apply search to sales
    if search_query and filter_type in ['all', 'sales']:
        pos_sales_qs = pos_sales_qs.filter(
            Q(sale_no__icontains=search_query) |
            Q(created_by__username__icontains=search_query)
        )
        invoices_qs = invoices_qs.filter(
            Q(invoice_number__icontains=search_query) |
            Q(created_by__username__icontains=search_query)
        )
    
    # Capital - Other Cash In
    # Status filter matches cashflow.monthly_signals._calculate_other_cash_in /
    # _calculate_capital_injections (both include PENDING) so the "Total"
    # footer — which reads summary.capital_other — always equals the sum of
    # the rows actually listed here.
    cash_in_txns_qs = CashFlowTransaction.objects.filter(
        status__in=[CashFlowStatus.APPROVED, CashFlowStatus.PENDING],
        flow_type=CashFlowType.CASH_IN,
        transaction_date__gte=start_date,
        transaction_date__lt=end_date,
    ).exclude(
        category=CashFlowCategory.SALES
    ).select_related('created_by', 'approved_by')
    
    # Apply search to cash in
    if search_query and filter_type in ['all', 'cash_in']:
        cash_in_txns_qs = cash_in_txns_qs.filter(
            Q(transaction_number__icontains=search_query) |
            Q(reason__icontains=search_query) |
            Q(reference_no__icontains=search_query)
        )
    
    # Expenses - Procurement
    grns_qs = GoodsReceipt.objects.filter(
        status=DocumentStatus.POSTED,
        receipt_date__gte=start_date,
        receipt_date__lt=end_date,
    ).select_related('supplier', 'warehouse', 'purchase_order').prefetch_related('lines')
    
    # Apply search to procurement
    if search_query and filter_type in ['all', 'procurement']:
        grns_qs = grns_qs.filter(
            Q(document_number__icontains=search_query) |
            Q(supplier__name__icontains=search_query)
        )
    
    # Expenses - Operational (exclude COGS/procurement expenses)
    expenses_qs = Expense.objects.filter(
        status='APPROVED',
        date__gte=start_date,
        date__lt=end_date,
        category__is_cogs=False,  # Exclude procurement/COGS expenses
    ).select_related('category', 'created_by')
    
    # Apply search to expenses
    if search_query and filter_type in ['all', 'expenses']:
        expenses_qs = expenses_qs.filter(
            Q(memo__icontains=search_query) |
            Q(vendor__icontains=search_query) |
            Q(category__name__icontains=search_query)
        )

    # summary.expenses_operational (cashflow.monthly_signals) is Expense-model
    # rows PLUS any CashFlowTransaction EXPENSES/SUPPLIES entries. Surface
    # those CF entries here too so the section "Total Operational" footer
    # isn't inflated by rows the page never actually shows.
    cf_operational_txns_qs = CashFlowTransaction.objects.filter(
        status__in=[CashFlowStatus.APPROVED, CashFlowStatus.PENDING],
        flow_type=CashFlowType.CASH_OUT,
        category__in=[CashFlowCategory.EXPENSES, CashFlowCategory.SUPPLIES],
        transaction_date__gte=start_date,
        transaction_date__lt=end_date,
    ).select_related('created_by', 'approved_by')

    if search_query and filter_type in ['all', 'expenses']:
        cf_operational_txns_qs = cf_operational_txns_qs.filter(
            Q(transaction_number__icontains=search_query) |
            Q(reason__icontains=search_query) |
            Q(reference_no__icontains=search_query)
        )
    
    # Expenses - Other Cash Out (EXCLUDE Procurement, Expenses, Supplies categories)
    # Status + category filters match cashflow.monthly_signals._calculate_other_cash_out
    # exactly so the "Total Other Cash Out" footer (summary.expenses_other)
    # always equals the sum of the rows listed here.
    cash_out_txns_qs = CashFlowTransaction.objects.filter(
        status__in=[CashFlowStatus.APPROVED, CashFlowStatus.PENDING],
        flow_type=CashFlowType.CASH_OUT,
        transaction_date__gte=start_date,
        transaction_date__lt=end_date,
    ).exclude(
        category__in=[
            CashFlowCategory.PROCUREMENT,
            CashFlowCategory.EXPENSES,
            CashFlowCategory.SUPPLIES,
        ]
    ).select_related('created_by', 'approved_by')
    
    # Apply search to cash out
    if search_query and filter_type in ['all', 'cash_out']:
        cash_out_txns_qs = cash_out_txns_qs.filter(
            Q(transaction_number__icontains=search_query) |
            Q(reason__icontains=search_query) |
            Q(reference_no__icontains=search_query)
        )
    
    # ── Build Breakdown Lists ────────────────────────────────────────────
    sales_breakdown = []
    
    # Only process if filter allows
    if filter_type in ['all', 'sales']:
        # POS Sales - handle missing items gracefully
        for sale in pos_sales_qs:
            try:
                revenue = sale.grand_total or Decimal('0')
                cogs = pos_sale_cogs(sale)  # Calculate COGS dynamically
                gross_profit = revenue - cogs
                sales_breakdown.append({
                    'type': 'POS Sale',
                    'number': sale.sale_no,
                    'date': sale.posted_at or sale.created_at,
                    'revenue': revenue,
                    'cogs': cogs,
                    'gross_profit': gross_profit,
                })
            except Exception as e:
                # Skip sales with missing items or other errors
                # Still add entry with zero COGS to show the sale exists
                sales_breakdown.append({
                    'type': 'POS Sale',
                    'number': sale.sale_no,
                    'date': sale.posted_at or sale.created_at,
                    'revenue': sale.grand_total or Decimal('0'),
                    'cogs': Decimal('0'),
                    'gross_profit': sale.grand_total or Decimal('0'),
                })
                continue
        
        # Invoices - handle missing data gracefully
        for inv in invoices_qs:
            try:
                revenue = inv.grand_total or Decimal('0')
                cogs = inv.grand_total_cogs or Decimal('0')
                gross_profit = revenue - cogs
                sales_breakdown.append({
                    'type': 'Invoice',
                    'number': inv.invoice_number,
                    'date': inv.date,
                    'revenue': revenue,
                    'cogs': cogs,
                    'gross_profit': gross_profit,
                    'flag': 'zero-revenue' if revenue == 0 and cogs > 0 else '',
                })
            except Exception:
                # Skip invoices with errors
                continue

        # Sales Returns — reduce revenue/COGS, matching cashflow.monthly_signals
        # (_calculate_sales_returns_revenue/_cogs) and cashflow.sync so this
        # table's total always agrees with summary.revenue_accrual/cogs_actual.
        from sales.models import SalesReturn
        from catalog.utils import calculate_line_cogs_with_conversion, convert_price_for_unit

        returns_qs = SalesReturn.objects.filter(
            status=DocumentStatus.POSTED,
            return_date__gte=start_date,
            return_date__lt=end_date,
        ).select_related('sales_order').prefetch_related('lines__item', 'lines__unit')

        if search_query and filter_type in ['all', 'sales']:
            returns_qs = returns_qs.filter(
                Q(document_number__icontains=search_query)
            )

        for sr in returns_qs:
            try:
                revenue = Decimal('0')
                cogs = Decimal('0')
                for line in sr.lines.all():
                    cogs += calculate_line_cogs_with_conversion(line.item, line.qty, line.unit)
                    unit_price = Decimal('0')
                    if sr.sales_order_id:
                        so_line = (
                            sr.sales_order.lines
                            .filter(item=line.item)
                            .select_related('unit')
                            .first()
                        )
                        if so_line:
                            if so_line.unit_id == line.unit_id:
                                unit_price = so_line.unit_price
                            else:
                                unit_price = convert_price_for_unit(
                                    so_line.unit_price, so_line.unit, line.unit, item=line.item,
                                )
                    if unit_price == 0:
                        unit_price = line.item.selling_price or Decimal('0')
                    revenue += unit_price * line.qty

                sales_breakdown.append({
                    'type': 'Sales Return',
                    'number': sr.document_number,
                    'date': sr.return_date,
                    'revenue': -revenue,
                    'cogs': -cogs,
                    'gross_profit': -revenue - (-cogs),
                })
            except Exception:
                continue

    procurement_breakdown = []
    if filter_type in ['all', 'procurement']:
        for grn in grns_qs:
            try:
                total_cost = Decimal('0')
                for line in grn.lines.all():
                    try:
                        line_cost = Decimal('0')
                        # Try PO price first
                        if grn.purchase_order:
                            po_line = grn.purchase_order.lines.filter(item=line.item).first()
                            if po_line and po_line.unit_price > 0:
                                line_cost = line.qty * po_line.unit_price
                        # Fall back to item cost_price
                        if line_cost == 0 and line.item.cost_price:
                            line_cost = line.qty * line.item.cost_price
                        total_cost += line_cost
                    except Exception:
                        continue
                # Include delivery charge
                if grn.delivery_charge:
                    total_cost += grn.delivery_charge
                procurement_breakdown.append({
                    'number': grn.document_number,
                    'date': grn.receipt_date,
                    'supplier': grn.supplier.name if grn.supplier else 'N/A',
                    'amount': total_cost,
                })
            except Exception:
                # Skip GRNs with errors
                continue
    
    # ── Pagination ───────────────────────────────────────────────────────
    # Paginate sales breakdown
    sales_paginator = Paginator(sales_breakdown, per_page)
    sales_page = request.GET.get('sales_page', 1)
    try:
        sales_breakdown_paginated = sales_paginator.page(sales_page)
    except PageNotAnInteger:
        sales_breakdown_paginated = sales_paginator.page(1)
    except EmptyPage:
        sales_breakdown_paginated = sales_paginator.page(sales_paginator.num_pages)
    
    # Paginate cash in transactions
    cash_in_paginator = Paginator(cash_in_txns_qs, per_page)
    cash_in_page = request.GET.get('cash_in_page', 1)
    try:
        cash_in_txns = cash_in_paginator.page(cash_in_page)
    except PageNotAnInteger:
        cash_in_txns = cash_in_paginator.page(1)
    except EmptyPage:
        cash_in_txns = cash_in_paginator.page(cash_in_paginator.num_pages)
    
    # Paginate procurement breakdown
    procurement_paginator = Paginator(procurement_breakdown, per_page)
    procurement_page = request.GET.get('procurement_page', 1)
    try:
        procurement_breakdown_paginated = procurement_paginator.page(procurement_page)
    except PageNotAnInteger:
        procurement_breakdown_paginated = procurement_paginator.page(1)
    except EmptyPage:
        procurement_breakdown_paginated = procurement_paginator.page(procurement_paginator.num_pages)
    
    # Paginate expenses
    expenses_paginator = Paginator(expenses_qs, per_page)
    expenses_page = request.GET.get('expenses_page', 1)
    try:
        expenses = expenses_paginator.page(expenses_page)
    except PageNotAnInteger:
        expenses = expenses_paginator.page(1)
    except EmptyPage:
        expenses = expenses_paginator.page(expenses_paginator.num_pages)
    
    # Paginate cash out transactions
    cash_out_paginator = Paginator(cash_out_txns_qs, per_page)
    cash_out_page = request.GET.get('cash_out_page', 1)
    try:
        cash_out_txns = cash_out_paginator.page(cash_out_page)
    except PageNotAnInteger:
        cash_out_txns = cash_out_paginator.page(1)
    except EmptyPage:
        cash_out_txns = cash_out_paginator.page(cash_out_paginator.num_pages)

    # Paginate CashFlowTransaction EXPENSES/SUPPLIES entries (part of
    # "Operational Expenses" for footer-total purposes — see cf_operational_txns_qs above)
    cf_operational_paginator = Paginator(cf_operational_txns_qs, per_page)
    cf_operational_page = request.GET.get('cf_operational_page', 1)
    try:
        cf_operational_txns = cf_operational_paginator.page(cf_operational_page)
    except PageNotAnInteger:
        cf_operational_txns = cf_operational_paginator.page(1)
    except EmptyPage:
        cf_operational_txns = cf_operational_paginator.page(cf_operational_paginator.num_pages)
    
    # Available months for navigation
    available_months = []
    for m in range(1, 13):
        available_months.append({
            'number': m,
            'name': month_name[m],
            'year': year,
        })
    
    # Available years
    available_years = list(range(year - 2, year + 2))
    
    context = {
        'summary': summary,
        'year': year,
        'month': month,
        'month_name': month_name[month],
        'available_months': available_months,
        'available_years': available_years,
        'sales_breakdown': sales_breakdown_paginated,
        'cash_in_txns': cash_in_txns,
        'procurement_breakdown': procurement_breakdown_paginated,
        'expenses': expenses,
        'cf_operational_txns': cf_operational_txns,
        'cash_out_txns': cash_out_txns,
        'search_query': search_query,
        'filter_type': filter_type,
        'per_page': per_page,
    }
    
    return render(request, 'cashflow/monthly_transaction_list.html', context)


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
@write_denied_for_viewer
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
            return redirect('cashflow:cashflow_list')
    else:
        form = CashFlowTransactionForm()
    return render(request, 'cashflow/transaction_form.html', {
        'form': form, 'title': 'New Cash Flow Transaction',
    })


# ═══════════════════════════════════════════════════════════════════════════
# TRANSACTION EDIT
# ═══════════════════════════════════════════════════════════════════════════
@login_required
@write_denied_for_viewer
def transaction_edit(request, pk):
    txn = get_object_or_404(CashFlowTransaction, pk=pk)
    if txn.status not in (CashFlowStatus.PENDING, CashFlowStatus.REJECTED):
        messages.warning(request, 'Only Pending or Rejected transactions can be edited.')
        return redirect('cashflow:cashflow_detail', pk=pk)

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
            return redirect('cashflow:cashflow_list')
    else:
        form = CashFlowTransactionForm(instance=txn)
    return render(request, 'cashflow/transaction_form.html', {
        'form': form, 'title': f'Edit: {txn.transaction_number}',
    })


# ═══════════════════════════════════════════════════════════════════════════
# TRANSACTION DELETE
# ═══════════════════════════════════════════════════════════════════════════
@login_required
@write_denied_for_viewer
def transaction_delete(request, pk):
    txn = get_object_or_404(CashFlowTransaction, pk=pk)
    if txn.status == CashFlowStatus.APPROVED:
        messages.warning(request, 'Approved transactions cannot be deleted.')
        return redirect('cashflow:cashflow_detail', pk=pk)

    if request.method == 'POST':
        _log(txn, CashFlowLogAction.DELETED, request.user,
             f'Transaction {txn.transaction_number} deleted.')
        txn.soft_delete()
        messages.success(request, f'Transaction {txn.transaction_number} deleted.')
        return redirect('cashflow:cashflow_list')
    return render(request, 'cashflow/transaction_delete.html', {'object': txn})


# ═══════════════════════════════════════════════════════════════════════════
# APPROVE / REJECT / CANCEL
# ═══════════════════════════════════════════════════════════════════════════
@login_required
@write_denied_for_viewer
def transaction_approve(request, pk):
    txn = get_object_or_404(CashFlowTransaction, pk=pk)
    if request.method != 'POST':
        return redirect('cashflow:cashflow_detail', pk=pk)
    if txn.status != CashFlowStatus.PENDING:
        messages.warning(request, 'Only Pending transactions can be approved.')
        return redirect('cashflow:cashflow_detail', pk=pk)

    txn.status = CashFlowStatus.APPROVED
    txn.approved_by = request.user
    txn.approved_at = timezone.now()
    txn.save(update_fields=['status', 'approved_by', 'approved_at', 'updated_at'])
    _log(txn, CashFlowLogAction.APPROVED, request.user,
         f'Transaction {txn.transaction_number} approved.')
    messages.success(request, f'Transaction {txn.transaction_number} approved.')
    return redirect('cashflow:cashflow_detail', pk=pk)


@login_required
@write_denied_for_viewer
def transaction_reject(request, pk):
    txn = get_object_or_404(CashFlowTransaction, pk=pk)
    if request.method != 'POST':
        return redirect('cashflow:cashflow_detail', pk=pk)
    if txn.status != CashFlowStatus.PENDING:
        messages.warning(request, 'Only Pending transactions can be rejected.')
        return redirect('cashflow:cashflow_detail', pk=pk)

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
    return redirect('cashflow:cashflow_detail', pk=pk)


@login_required
@write_denied_for_viewer
def transaction_cancel(request, pk):
    txn = get_object_or_404(CashFlowTransaction, pk=pk)
    if request.method != 'POST':
        return redirect('cashflow:cashflow_detail', pk=pk)
    if txn.status == CashFlowStatus.CANCELLED:
        messages.warning(request, 'Transaction is already cancelled.')
        return redirect('cashflow:cashflow_detail', pk=pk)

    old_status = txn.status
    txn.status = CashFlowStatus.CANCELLED
    txn.save(update_fields=['status', 'updated_at'])
    _log(txn, CashFlowLogAction.CANCELLED, request.user,
         f'Transaction {txn.transaction_number} cancelled (was {old_status}).')
    messages.success(request, f'Transaction {txn.transaction_number} cancelled.')
    return redirect('cashflow:cashflow_detail', pk=pk)


# ═══════════════════════════════════════════════════════════════════════════
# CASH FLOW LOGS
# ═══════════════════════════════════════════════════════════════════════════
@login_required
def log_list(request):
    from core.utils import sort_queryset, paginate_queryset, search_queryset
    qs = CashFlowLog.objects.select_related('transaction', 'performed_by')

    qs = search_queryset(request, qs, [
        'transaction__transaction_number', 'performed_by__username', 'details',
    ])
    action_filter = (request.GET.get('action') or '').strip()
    if action_filter:
        qs = qs.filter(action=action_filter)

    sort_map = {
        'date': 'created_at',
        'transaction': 'transaction__transaction_number',
        'action': 'action',
        'performed_by': 'performed_by__username',
    }
    qs, sort, direction = sort_queryset(request, qs, sort_map, default_key='created_at', default_dir='desc')
    page_obj = paginate_queryset(request, qs, per_page=25)

    filters = [{
        'param': 'action',
        'label': 'Action',
        'options': list(CashFlowLogAction.choices),
    }]

    return render(request, 'cashflow/log_list.html', {
        'logs': page_obj,
        'page_obj': page_obj,
        'sort': sort,
        'dir': direction,
        'filters': filters,
    })


# ═══════════════════════════════════════════════════════════════════════════
# SYNC — Full cash-flow recalculation (sales + procurement + expenses)
# ═══════════════════════════════════════════════════════════════════════════
@login_required
@write_denied_for_viewer
def sync_cashflow(request):
    """
    POST-only AJAX view.  Rebuilds daily sales revenue entries and
    backfills any missing GoodsReceipt, PurchaseReturn, and Expense entries.
    Returns JSON so the frontend can show results via Swal.fire.
    """
    if request.method != 'POST':
        return redirect('cashflow:cashflow_list')

    from cashflow.sync import sync_all
    try:
        result = sync_all(request.user)
    except Exception as exc:
        return JsonResponse({
            'success': False,
            'message': f'Sync failed: {exc}',
        }, status=500)

    parts = []
    if result['sales']:
        parts.append(f"{result['sales']} daily sales entr{'y' if result['sales'] == 1 else 'ies'}")
    if result['grn']:
        parts.append(f"{result['grn']} goods receipt(s)")
    if result['purchase_return']:
        parts.append(f"{result['purchase_return']} purchase return(s)")
    if result['expense']:
        parts.append(f"{result['expense']} expense(s)")

    if result['errors']:
        return JsonResponse({
            'success': False,
            'message': ' | '.join(result['errors']),
            'detail': ', '.join(parts) if parts else None,
        }, status=500)

    total = result['sales'] + result['grn'] + result['purchase_return'] + result['expense']
    summary = ', '.join(parts) if parts else 'Everything is up to date'
    return JsonResponse({
        'success': True,
        'message': f'Cash flow sync complete — {total} entries created.',
        'detail': summary,
    })
