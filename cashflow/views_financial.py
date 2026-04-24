"""
Financial Dashboard Views
==========================
Modern, performant views for financial reporting with best UI/UX practices.
"""
from decimal import Decimal
from datetime import date
from calendar import month_name

from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Q
from django.http import JsonResponse

from cashflow.models import MonthlyCashflowSummary
from core.models import Invoice


@login_required
def financial_dashboard(request):
    """
    Main financial dashboard with overview cards and charts.
    Optimized for performance with minimal database queries.
    """
    # Get current year and month
    today = date.today()
    current_year = request.GET.get('year', today.year)
    current_month = request.GET.get('month', today.month)
    
    try:
        current_year = int(current_year)
        current_month = int(current_month)
    except (ValueError, TypeError):
        current_year = today.year
        current_month = today.month
    
    # Get current month summary
    current_summary = MonthlyCashflowSummary.objects.filter(
        year=current_year,
        month=current_month
    ).first()
    
    # Get previous month for comparison
    if current_month == 1:
        prev_year, prev_month = current_year - 1, 12
    else:
        prev_year, prev_month = current_year, current_month - 1
    
    prev_summary = MonthlyCashflowSummary.objects.filter(
        year=prev_year,
        month=prev_month
    ).first()
    
    # Get year-to-date summaries
    ytd_summaries = MonthlyCashflowSummary.objects.filter(
        year=current_year,
        month__lte=current_month
    ).order_by('month')
    
    # Calculate YTD totals
    ytd_revenue = sum(s.revenue_accrual for s in ytd_summaries)
    ytd_cogs = sum(s.cogs_actual for s in ytd_summaries)
    ytd_gross_profit = ytd_revenue - ytd_cogs
    ytd_net_profit = sum(s.net_profit for s in ytd_summaries)
    ytd_cash_flow = sum(s.operating_cash_flow for s in ytd_summaries)
    
    # Calculate trends (vs previous month)
    trends = {}
    if current_summary and prev_summary:
        trends['revenue'] = _calculate_trend(current_summary.revenue_accrual, prev_summary.revenue_accrual)
        trends['profit'] = _calculate_trend(current_summary.net_profit, prev_summary.net_profit)
        trends['cash_flow'] = _calculate_trend(current_summary.operating_cash_flow, prev_summary.operating_cash_flow)
        trends['margin'] = _calculate_trend(current_summary.gross_margin_pct, prev_summary.gross_margin_pct)
    
    # Get available years and months for navigation
    available_periods = MonthlyCashflowSummary.objects.values_list('year', 'month').distinct().order_by('-year', '-month')
    
    context = {
        'current_year': current_year,
        'current_month': current_month,
        'current_month_name': month_name[current_month],
        'current_summary': current_summary,
        'prev_summary': prev_summary,
        'ytd_summaries': ytd_summaries,
        'ytd_revenue': ytd_revenue,
        'ytd_cogs': ytd_cogs,
        'ytd_gross_profit': ytd_gross_profit,
        'ytd_net_profit': ytd_net_profit,
        'ytd_cash_flow': ytd_cash_flow,
        'trends': trends,
        'available_periods': available_periods,
    }
    
    return render(request, 'cashflow/financial_dashboard.html', context)


@login_required
def cash_flow_statement(request, year, month):
    """
    Detailed cash flow statement view.
    Shows actual cash movement with operating, investing, and financing activities.
    """
    summary = MonthlyCashflowSummary.objects.filter(year=year, month=month).first()
    
    if not summary:
        return render(request, 'cashflow/statement_not_found.html', {
            'year': year,
            'month': month,
            'month_name': month_name[month],
        })
    
    context = {
        'year': year,
        'month': month,
        'month_name': month_name[month],
        'summary': summary,
    }
    
    return render(request, 'cashflow/cash_flow_statement.html', context)


@login_required
def profit_loss_statement(request, year, month):
    """
    Detailed profit & loss statement view.
    Shows accrual-basis revenue and expenses.
    """
    summary = MonthlyCashflowSummary.objects.filter(year=year, month=month).first()
    
    if not summary:
        return render(request, 'cashflow/statement_not_found.html', {
            'year': year,
            'month': month,
            'month_name': month_name[month],
        })
    
    context = {
        'year': year,
        'month': month,
        'month_name': month_name[month],
        'summary': summary,
    }
    
    return render(request, 'cashflow/profit_loss_statement.html', context)


@login_required
def balance_sheet(request, year, month):
    """
    Balance sheet view showing assets, liabilities, and equity.
    """
    summary = MonthlyCashflowSummary.objects.filter(year=year, month=month).first()
    
    if not summary:
        return render(request, 'cashflow/statement_not_found.html', {
            'year': year,
            'month': month,
            'month_name': month_name[month],
        })
    
    # Calculate total assets
    total_assets = (
        summary.cash_closing +
        summary.inventory_value_closing +
        summary.accounts_receivable_closing
    )
    
    # Calculate total liabilities
    total_liabilities = summary.accounts_payable_closing
    
    # Calculate equity (Assets - Liabilities)
    equity = total_assets - total_liabilities
    
    context = {
        'year': year,
        'month': month,
        'month_name': month_name[month],
        'summary': summary,
        'total_assets': total_assets,
        'total_liabilities': total_liabilities,
        'equity': equity,
    }
    
    return render(request, 'cashflow/balance_sheet.html', context)


@login_required
def financial_metrics_api(request):
    """
    API endpoint for financial metrics (for charts and real-time updates).
    Returns JSON data optimized for frontend charting libraries.
    """
    year = int(request.GET.get('year', date.today().year))
    
    # Get all months for the year
    summaries = MonthlyCashflowSummary.objects.filter(year=year).order_by('month')
    
    # Prepare data for charts
    data = {
        'labels': [month_name[s.month] for s in summaries],
        'revenue': [float(s.revenue_accrual) for s in summaries],
        'cogs': [float(s.cogs_actual) for s in summaries],
        'gross_profit': [float(s.gross_profit) for s in summaries],
        'net_profit': [float(s.net_profit) for s in summaries],
        'cash_flow': [float(s.operating_cash_flow) for s in summaries],
        'cash_balance': [float(s.cash_closing) for s in summaries],
        'inventory_value': [float(s.inventory_value_closing) for s in summaries],
        'ar_balance': [float(s.accounts_receivable_closing) for s in summaries],
        'gross_margin': [float(s.gross_margin_pct) for s in summaries],
        'collection_rate': [float(s.collection_rate_pct) for s in summaries],
    }
    
    return JsonResponse(data)


def _calculate_trend(current, previous):
    """Calculate percentage change and direction."""
    if previous == 0:
        return {'change': 0, 'direction': 'neutral', 'percentage': 0}
    
    change = current - previous
    percentage = (change / previous) * 100
    
    if change > 0:
        direction = 'up'
    elif change < 0:
        direction = 'down'
    else:
        direction = 'neutral'
    
    return {
        'change': float(change),
        'direction': direction,
        'percentage': float(percentage),
    }
