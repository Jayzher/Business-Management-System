"""
Monthly Cashflow Views
======================
Dashboard and detailed views for monthly cashflow summaries.
"""
import json
from datetime import date, datetime
from decimal import Decimal
from calendar import month_name

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Sum, Q
from django.http import JsonResponse
from accounts.decorators import write_denied_for_viewer
from django.core.management import call_command
from io import StringIO

from cashflow.models import MonthlyCashflowSummary, CashFlowTransaction, CashFlowType, CashFlowStatus, CashFlowCategory
from core.models import Expense
from pos.models import POSSale, SaleStatus
from procurement.models import GoodsReceipt
from core.models import DocumentStatus


@login_required
def monthly_dashboard(request):
    """Main dashboard showing monthly cashflow summaries with charts."""
    from cashflow.monthly_signals import update_monthly_summary
    from datetime import date
    
    # Get year filter (default: current year)
    current_year = date.today().year
    year = int(request.GET.get('year', current_year))
    
    # Get all summaries for the year
    summaries = MonthlyCashflowSummary.objects.filter(year=year).order_by('month')
    
    # Auto-create missing months if requested
    if request.GET.get('auto_create') == '1':
        existing_months = set(summaries.values_list('month', flat=True))
        for month in range(1, 13):
            if month not in existing_months:
                # Check if there's any data for this month
                start_date = date(year, month, 1)
                if month == 12:
                    next_month = date(year + 1, 1, 1)
                else:
                    next_month = date(year, month + 1, 1)
                
                # Only create if there's transaction data
                from pos.models import POSSale, SaleStatus
                has_data = POSSale.objects.filter(
                    status=SaleStatus.POSTED,
                    created_at__gte=start_date,
                    created_at__lt=next_month,
                ).exists()
                
                if has_data:
                    update_monthly_summary(year, month, user=request.user)
        
        # Refresh summaries after auto-creation
        summaries = MonthlyCashflowSummary.objects.filter(year=year).order_by('month')
    
    # Calculate year totals
    year_totals = summaries.aggregate(
        revenue_accrual=Sum('revenue_accrual'),
        gross_profit=Sum('gross_profit'),
        net_profit=Sum('net_profit'),
        operating_cash_flow=Sum('operating_cash_flow'),
        collection_rate_pct=Sum('collection_rate_pct'),
        accounts_receivable_closing=Sum('accounts_receivable_closing'),
        inventory_value_closing=Sum('inventory_value_closing'),
        gross_margin_pct=Sum('gross_margin_pct'),
    )
    
    # Get available years
    available_years = (
        MonthlyCashflowSummary.objects
        .values_list('year', flat=True)
        .distinct()
        .order_by('-year')
    )
    
    # If no years exist, add current year
    if not available_years:
        available_years = [current_year]
    
    # Prepare chart data
    chart_data = {
        'labels': [month_name[s.month] for s in summaries],
        'revenue': [float(s.revenue_accrual or 0) for s in summaries],
        'gross_profit': [float(s.gross_profit or 0) for s in summaries],
        'net_profit': [float(s.net_profit or 0) for s in summaries],
        'cash_flow': [float(s.operating_cash_flow or 0) for s in summaries],
    }
    
    context = {
        'summaries': summaries,
        'year': year,
        'available_years': available_years,
        'year_totals': year_totals,
        'chart_data': json.dumps(chart_data),  # Serialize to JSON string
        'current_year': current_year,
    }
    
    # ── Capital ROI Analysis ─────────────────────────────────────────────
    context.update(_build_capital_roi_context(year))
    
    return render(request, 'cashflow/monthly_dashboard.html', context)


def _build_capital_roi_context(year):
    """
    Build the Capital ROI analysis context for the dashboard.
    Answers: "How much profit did the capital actually generate?"
    """
    from datetime import date
    from core.models import Invoice, InvoicePayment
    from inventory.models import StockBalance
    from decimal import Decimal
    from django.db.models import Sum
    from django.db.models.functions import Coalesce

    start = date(year, 1, 1)
    end = date(year + 1, 1, 1)
    today = date.today()
    if today < end:
        end = date(today.year, today.month + 1, 1) if today.month < 12 else date(today.year + 1, 1, 1)

    # Capital injected
    capital = CashFlowTransaction.objects.filter(
        flow_type=CashFlowType.CASH_IN,
        category=CashFlowCategory.CAPITAL,
        transaction_date__gte=start, transaction_date__lt=end,
        status__in=[CashFlowStatus.APPROVED, 'PENDING'],
    ).aggregate(t=Sum('amount'))['t'] or Decimal('0')

    # Revenue collected (actual cash from customers)
    inv_payments = InvoicePayment.objects.filter(
        date__gte=start, date__lt=end,
    ).aggregate(t=Sum('amount'))['t'] or Decimal('0')

    from django.utils import timezone
    start_dt = timezone.make_aware(datetime.combine(start, datetime.min.time()))
    end_dt = timezone.make_aware(datetime.combine(end, datetime.min.time()))

    pos_cash = POSSale.objects.filter(
        status=SaleStatus.POSTED,
        posted_at__gte=start_dt, posted_at__lt=end_dt,
    ).aggregate(t=Sum('grand_total'))['t'] or Decimal('0')

    revenue_collected = inv_payments + pos_cash

    # COGS from invoices (what was actually sold)
    invoice_cogs = Invoice.objects.filter(
        is_void=False, date__gte=start, date__lt=end,
    ).aggregate(t=Coalesce(Sum('grand_total_cogs'), Decimal('0')))['t']

    # Operating expenses
    opex = CashFlowTransaction.objects.filter(
        flow_type=CashFlowType.CASH_OUT,
        category=CashFlowCategory.EXPENSES,
        transaction_date__gte=start, transaction_date__lt=end,
        status__in=[CashFlowStatus.APPROVED, 'PENDING'],
    ).aggregate(t=Sum('amount'))['t'] or Decimal('0')

    other_out = CashFlowTransaction.objects.filter(
        flow_type=CashFlowType.CASH_OUT,
        transaction_date__gte=start, transaction_date__lt=end,
        status__in=[CashFlowStatus.APPROVED, 'PENDING'],
    ).exclude(category__in=[
        CashFlowCategory.PROCUREMENT, CashFlowCategory.EXPENSES, CashFlowCategory.SUPPLIES,
    ]).aggregate(t=Sum('amount'))['t'] or Decimal('0')

    total_opex = opex + other_out

    # Procurement spent
    procurement_spent = CashFlowTransaction.objects.filter(
        flow_type=CashFlowType.CASH_OUT,
        category=CashFlowCategory.PROCUREMENT,
        transaction_date__gte=start, transaction_date__lt=end,
        status__in=[CashFlowStatus.APPROVED, 'PENDING'],
    ).aggregate(t=Sum('amount'))['t'] or Decimal('0')

    # Current inventory value
    inventory_value = Decimal('0')
    for bal in StockBalance.objects.filter(qty_on_hand__gt=Decimal('0.001')).select_related('item'):
        inventory_value += bal.qty_on_hand * (bal.item.cost_price or Decimal('0'))

    # Accounts receivable
    ar = Decimal('0')
    for inv in Invoice.objects.filter(is_void=False, date__lt=end).prefetch_related('payments'):
        paid = sum(p.amount for p in inv.payments.filter(date__lt=end))
        balance = inv.grand_total - paid
        if balance > 0:
            ar += balance

    # Calculations
    gross_profit = revenue_collected - invoice_cogs
    gross_margin = (gross_profit / revenue_collected * 100) if revenue_collected > 0 else Decimal('0')
    net_profit = revenue_collected - invoice_cogs - total_opex
    net_margin = (net_profit / revenue_collected * 100) if revenue_collected > 0 else Decimal('0')

    # Hold scenario
    hold_cash = capital + revenue_collected - invoice_cogs - total_opex
    roi_on_capital = (net_profit / capital * 100) if capital > 0 else Decimal('0')

    # Actual position — cumulative net cash ledger position as of `end`
    # (all-time cash in minus all-time cash out, not just this year's),
    # using the same APPROVED+PENDING convention as every other cash-basis
    # figure in this module.
    actual_cash_in = CashFlowTransaction.objects.filter(
        flow_type=CashFlowType.CASH_IN,
        transaction_date__lt=end,
        status__in=[CashFlowStatus.APPROVED, 'PENDING'],
    ).aggregate(t=Sum('amount'))['t'] or Decimal('0')
    actual_cash_out = CashFlowTransaction.objects.filter(
        flow_type=CashFlowType.CASH_OUT,
        transaction_date__lt=end,
        status__in=[CashFlowStatus.APPROVED, 'PENDING'],
    ).aggregate(t=Sum('amount'))['t'] or Decimal('0')
    actual_cash = actual_cash_in - actual_cash_out
    total_assets = actual_cash + inventory_value + ar
    equity_gain = total_assets - capital
    equity_roi = (equity_gain / capital * 100) if capital > 0 else Decimal('0')

    # Capital allocation percentages
    cash_pct = (actual_cash / capital * 100) if capital > 0 else Decimal('0')
    inv_pct = (inventory_value / capital * 100) if capital > 0 else Decimal('0')
    ar_pct = (ar / capital * 100) if capital > 0 else Decimal('0')

    return {
        'roi_capital': capital,
        'roi_revenue': revenue_collected,
        'roi_cogs': invoice_cogs,
        'roi_gross_profit': gross_profit,
        'roi_gross_margin': gross_margin,
        'roi_opex': total_opex,
        'roi_net_profit': net_profit,
        'roi_net_margin': net_margin,
        'roi_hold_cash': hold_cash,
        'roi_on_capital': roi_on_capital,
        'roi_procurement': procurement_spent,
        'roi_inventory': inventory_value,
        'roi_ar': ar,
        'roi_actual_cash': actual_cash,
        'roi_total_assets': total_assets,
        'roi_equity_gain': equity_gain,
        'roi_equity_roi': equity_roi,
        'roi_cash_pct': cash_pct,
        'roi_inv_pct': inv_pct,
        'roi_ar_pct': ar_pct,
    }


@login_required
def monthly_detail(request, year, month):
    """Detailed breakdown for a specific month."""
    from cashflow.monthly_signals import update_monthly_summary
    
    # Try to get existing summary, or create it automatically
    try:
        summary = MonthlyCashflowSummary.objects.get(year=year, month=month)
    except MonthlyCashflowSummary.DoesNotExist:
        # Auto-create the summary
        summary = update_monthly_summary(year, month, user=request.user)
    
    # Date range
    if month == 12:
        next_month = date(year + 1, 1, 1)
    else:
        next_month = date(year, month + 1, 1)
    start_date = date(year, month, 1)
    end_date = next_month
    
    # Get detailed transactions
    cash_in_transactions = CashFlowTransaction.objects.filter(
        status__in=[CashFlowStatus.APPROVED, 'PENDING'],
        flow_type=CashFlowType.CASH_IN,
        transaction_date__gte=start_date,
        transaction_date__lt=end_date,
    ).exclude(
        category=CashFlowCategory.SALES
    ).order_by('-transaction_date')
    
    cash_out_transactions = CashFlowTransaction.objects.filter(
        status__in=[CashFlowStatus.APPROVED, 'PENDING'],
        flow_type=CashFlowType.CASH_OUT,
        transaction_date__gte=start_date,
        transaction_date__lt=end_date,
    ).order_by('-transaction_date')
    
    # Get sales
    pos_sales = POSSale.objects.filter(
        status=SaleStatus.POSTED,
        created_at__gte=start_date,
        created_at__lt=end_date,
    ).order_by('-created_at')
    
    # Get procurements
    procurements = GoodsReceipt.objects.filter(
        status=DocumentStatus.POSTED,
        receipt_date__gte=start_date,
        receipt_date__lt=end_date,
    ).select_related('supplier', 'warehouse').order_by('-receipt_date')
    
    # Get operational expenses (exclude COGS/procurement expenses)
    expenses = Expense.objects.filter(
        status='APPROVED',
        date__gte=start_date,
        date__lt=end_date,
        category__is_cogs=False,  # Only operational expenses, not procurement
    ).select_related('category').order_by('-date')
    
    context = {
        'summary': summary,
        'cash_in_transactions': cash_in_transactions,
        'cash_out_transactions': cash_out_transactions,
        'pos_sales': pos_sales,
        'procurements': procurements,
        'expenses': expenses,  # Operational expenses only
    }
    
    return render(request, 'cashflow/monthly_detail.html', context)


@login_required
@write_denied_for_viewer
def recalculate_month(request, year, month):
    """Recalculate a specific month's summary."""
    from cashflow.monthly_signals import update_monthly_summary
    
    if request.method == 'POST':
        try:
            update_monthly_summary(year, month, user=request.user)
            messages.success(request, f'Successfully recalculated {month_name[month]} {year}')
        except Exception as e:
            messages.error(request, f'Error recalculating: {str(e)}')
    
    return redirect('cashflow:monthly_detail', year=year, month=month)


@login_required
def recalculate_all(request):
    """Recalculate all monthly summaries."""
    from cashflow.monthly_signals import update_monthly_summary
    
    if request.method == 'POST':
        try:
            # Get all existing summaries
            summaries = MonthlyCashflowSummary.objects.all()
            count = 0
            for summary in summaries:
                update_monthly_summary(summary.year, summary.month, user=request.user)
                count += 1
            
            messages.success(request, f'Successfully recalculated {count} monthly summaries')
        except Exception as e:
            messages.error(request, f'Error recalculating: {str(e)}')
    
    return redirect('cashflow:monthly_dashboard')


@login_required
def monthly_chart_data(request, year):
    """API endpoint for chart data."""
    summaries = MonthlyCashflowSummary.objects.filter(year=year).order_by('month')
    
    data = {
        'labels': [month_name[s.month] for s in summaries],
        'datasets': [
            {
                'label': 'Capital',
                'data': [float(s.capital_total) for s in summaries],
                'backgroundColor': 'rgba(34, 197, 94, 0.2)',
                'borderColor': 'rgb(34, 197, 94)',
                'borderWidth': 2,
            },
            {
                'label': 'Expenses',
                'data': [float(s.expenses_total) for s in summaries],
                'backgroundColor': 'rgba(239, 68, 68, 0.2)',
                'borderColor': 'rgb(239, 68, 68)',
                'borderWidth': 2,
            },
            {
                'label': 'Net Profit',
                'data': [float(s.net_profit) for s in summaries],
                'backgroundColor': 'rgba(59, 130, 246, 0.2)',
                'borderColor': 'rgb(59, 130, 246)',
                'borderWidth': 2,
            },
        ]
    }
    
    return JsonResponse(data)


@login_required
def auto_create_summary(request, year, month):
    """API endpoint to auto-create a summary for a specific month."""
    from cashflow.monthly_signals import update_monthly_summary
    
    if request.method == 'POST':
        try:
            summary = update_monthly_summary(year, month, user=request.user)
            return JsonResponse({
                'success': True,
                'message': f'Created summary for {month_name[month]} {year}',
                'data': {
                    'capital_total': float(summary.capital_total),
                    'expenses_total': float(summary.expenses_total),
                    'net_profit': float(summary.net_profit),
                }
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': str(e)
            }, status=400)
    
    return JsonResponse({'success': False, 'message': 'POST required'}, status=405)
