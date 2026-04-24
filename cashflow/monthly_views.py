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
    
    return render(request, 'cashflow/monthly_dashboard.html', context)


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
        status=CashFlowStatus.APPROVED,
        flow_type=CashFlowType.CASH_IN,
        transaction_date__gte=start_date,
        transaction_date__lt=end_date,
    ).exclude(
        category=CashFlowCategory.SALES
    ).order_by('-transaction_date')
    
    cash_out_transactions = CashFlowTransaction.objects.filter(
        status=CashFlowStatus.APPROVED,
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
