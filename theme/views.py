from decimal import Decimal
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Count, Q, F, DecimalField
from django.db.models.functions import Coalesce
from django.utils import timezone
from datetime import timedelta
from core.cogs import compute_invoice_cogs


@login_required
def dashboard_view(request):
    # Viewer-only users cannot access the dashboard — redirect to catalog
    from accounts.decorators import _user_is_viewer
    if _user_is_viewer(request.user):
        return redirect('item_list')

    from catalog.models import Item
    from inventory.models import StockBalance, StockMove
    from procurement.models import GoodsReceipt
    from sales.models import DeliveryNote, SalesOrder, SalesOrderLine, SalesOrderPriceListLine
    from pos.models import POSSale, POSSaleLine, POSShift, SaleStatus, ShiftStatus
    from core.models import Expense, ExpenseCategory, TargetGoal, SalesChannel, Invoice, DocumentStatus

    now = timezone.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # ── Period toggle (today / week / month / year) ────────────────────
    # Week = Monday to Sunday of current week; Month = 1st to last day of current month
    period = request.GET.get('period', 'today')
    if period == 'week':
        # Monday of current week
        period_start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        # Sunday end of current week (Monday + 6 days, end of day)
        period_end = (period_start + timedelta(days=7)).replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == 'month':
        period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        # First day of next month
        if now.month == 12:
            period_end = now.replace(year=now.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        else:
            period_end = now.replace(month=now.month + 1, day=1, hour=0, minute=0, second=0, microsecond=0)
    elif period == 'year':
        period_start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        period_end = now.replace(year=now.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        period_start = today_start
        period_end = today_start + timedelta(days=1)  # End of today
        period = 'today'

    total_items = Item.objects.filter(is_active=True).count()

    low_stock_count = 0
    items_with_reorder = Item.objects.filter(is_active=True, reorder_point__gt=0)
    for item in items_with_reorder:
        total_on_hand = StockBalance.objects.filter(item=item).aggregate(
            total=Sum('qty_on_hand')
        )['total'] or 0
        if total_on_hand <= item.reorder_point:
            low_stock_count += 1

    pending_grns = GoodsReceipt.objects.filter(status='DRAFT').count()
    pending_deliveries = DeliveryNote.objects.filter(status='DRAFT').count()

    thirty_days_ago = now - timedelta(days=30)
    recent_moves = StockMove.objects.filter(
        status='POSTED', posted_at__gte=thirty_days_ago
    ).values('move_type').annotate(count=Count('id')).order_by('move_type')

    latest_transactions = StockMove.objects.filter(
        status='POSTED'
    ).select_related('item', 'created_by')[:10]

    # ── Revenue & COGS from PAYMENTS in period ──────────────────────────
    # Payment-based revenue recognition: count actual InvoicePayment
    # records that fall within the period, not full grand_total when
    # is_paid=True. This matches the Financial Statement (P&L) approach
    # and prevents double-counting of partial payments.
    from core.models import InvoicePayment

    period_payments = InvoicePayment.objects.filter(
        invoice__is_void=False,
        date__gte=period_start.date(),
        date__lt=period_end.date(),
    )

    # Sum payments per invoice within the period
    payments_by_invoice = dict(
        period_payments.values_list('invoice_id').annotate(
            period_paid=Coalesce(Sum('amount'), Decimal('0'), output_field=DecimalField())
        ).values_list('invoice_id', 'period_paid')
    )

    # Total payment-based revenue and discount
    total_payments_in_period = period_payments.aggregate(
        total=Coalesce(Sum('amount'), Decimal('0'), output_field=DecimalField())
    )['total']

    # Load invoice objects for COGS calculation
    invoice_ids_in_period = set(payments_by_invoice.keys())
    period_invoice_rows = list(
        Invoice.objects.filter(pk__in=invoice_ids_in_period, is_void=False)
        .select_related('pos_sale', 'sales_order')
        .prefetch_related(
            'customer_services__lines__item',
            'customer_services__lines__unit',
            'customer_services__bundles__price_list__items__item',
            'customer_services__bundles__price_list__items__unit',
            'customer_services__other_materials',
            'pos_sale__lines__item',
            'pos_sale__lines__unit',
            'pos_sale__bundle_lines__price_list__items__item',
            'pos_sale__bundle_lines__price_list__items__unit',
            'sales_order__lines__item',
            'sales_order__lines__unit',
            'sales_order__price_list_lines__price_list__items__item',
            'sales_order__price_list_lines__price_list__items__unit',
        )
    )

    # Calculate proportional COGS and discount based on payment ratio
    invoice_cogs_total = Decimal('0')
    total_discount = Decimal('0')
    for inv in period_invoice_rows:
        period_paid = payments_by_invoice.get(inv.pk, Decimal('0'))
        ratio = (period_paid / inv.grand_total) if inv.grand_total > 0 else Decimal('0')
        if ratio > Decimal('1.0'):
            ratio = Decimal('1.0')
        full_cogs = compute_invoice_cogs(inv)
        invoice_cogs_total += (full_cogs * ratio).quantize(Decimal('0.01'))
        total_discount += (inv.discount_total * ratio).quantize(Decimal('0.01'))

    combined_revenue = total_payments_in_period - total_discount
    combined_count = len(invoice_ids_in_period)
    combined_profit = combined_revenue - invoice_cogs_total
    pos_margin = (combined_profit / combined_revenue * 100) if combined_revenue > 0 else Decimal('0')

    # Keep POS sales queryset for channel breakdown and top-items widgets (non-revenue)
    from reports.views import _with_pos_sale_refunds, _with_pos_line_refunds
    period_sales = _with_pos_sale_refunds(POSSale.objects.filter(
        status__in=[SaleStatus.POSTED, SaleStatus.PAID, SaleStatus.PARTIALLY_REFUNDED],
        created_at__gte=period_start,
        created_at__lt=period_end,
    ))
    pos_count = period_sales.count()
    pos_revenue = Decimal('0')
    so_count = 0
    so_revenue = Decimal('0')
    pos_cogs = invoice_cogs_total
    pos_profit = combined_profit
    so_cogs = Decimal('0')
    so_profit = Decimal('0')

    # Invoice count for widgets
    invoice_paid_count = combined_count

    # ── Expenses for selected period ───────────────────────────────────
    period_expenses = Expense.objects.filter(
        date__gte=period_start.date(),
        date__lt=period_end.date(),
    )
    total_expenses = period_expenses.aggregate(
        total=Coalesce(Sum('amount'), Decimal('0'), output_field=DecimalField())
    )['total']
    net_profit = combined_profit - total_expenses

    # Expense by category (top 5)
    expense_by_cat = period_expenses.values('category__name').annotate(
        total=Coalesce(Sum('amount'), Decimal('0'), output_field=DecimalField())
    ).order_by('-total')[:5]
    exp_cat_labels = [r['category__name'] for r in expense_by_cat]
    exp_cat_data = [float(r['total']) for r in expense_by_cat]

    # ── Sales by channel ───────────────────────────────────────────────
    channel_breakdown = period_sales.values('channel__name').annotate(
        total=Coalesce(Sum(F('grand_total') - F('refunded_amount')), Decimal('0'), output_field=DecimalField()),
        count=Count('id'),
    ).order_by('-total')
    ch_labels = [r['channel__name'] or 'No Channel' for r in channel_breakdown]
    ch_data = [float(r['total']) for r in channel_breakdown]

    # ── Top items sold ─────────────────────────────────────────────────
    top_items = _with_pos_line_refunds(POSSaleLine.objects.filter(sale__in=period_sales)).values(
        'item__code', 'item__name'
    ).annotate(
        total_qty=Sum(F('qty') - F('refunded_qty')),
        total_revenue=Sum(F('line_total') - F('refunded_amount')),
    ).order_by('-total_revenue')[:5]

    # Open shifts
    open_shifts = POSShift.objects.filter(status=ShiftStatus.OPEN).select_related('register', 'opened_by')

    # ── Inventory valuation (exact calculation from Inventory module) ────────────────────────────────────────────
    from catalog.models import Item
    inventory_valuation = Decimal('0')
    for item in Item.objects.filter(is_active=True).select_related('default_unit'):
        total_on_hand = StockBalance.objects.filter(item=item).aggregate(
            total=Coalesce(Sum('qty_on_hand'), Decimal('0'))
        )['total'] or Decimal('0')
        inventory_valuation += total_on_hand * (item.cost_price or Decimal('0'))

    # ── 7-day revenue trend (payments by date) ─────────────────────────
    revenue_trend = []
    for i in range(6, -1, -1):
        day = (now - timedelta(days=i)).date()
        day_rev = InvoicePayment.objects.filter(
            invoice__is_void=False, date=day,
        ).aggregate(
            total=Coalesce(Sum('amount'), Decimal('0'), output_field=DecimalField())
        )['total']
        revenue_trend.append({'date': day.strftime('%b %d'), 'revenue': float(day_rev)})

    # ── Active goals ───────────────────────────────────────────────────
    active_goals = TargetGoal.objects.filter(
        status__in=['PENDING', 'IN_PROGRESS']
    ).order_by('-priority', 'due_date')[:5]

    # ── Pending approvals widget ─────────────────────────────────────
    from procurement.models import PurchaseOrder
    from inventory.models import StockTransfer, StockAdjustment
    pending_po = PurchaseOrder.objects.filter(status='DRAFT').count()
    pending_so = SalesOrder.objects.filter(status='DRAFT').count()
    pending_grn_draft = GoodsReceipt.objects.filter(status='DRAFT').count()
    pending_dn_draft = DeliveryNote.objects.filter(status='DRAFT').count()
    pending_approvals_total = pending_po + pending_so + pending_grn_draft + pending_dn_draft

    # ── Unpaid invoices widget ───────────────────────────────────────
    unpaid_invoices = Invoice.objects.filter(is_paid=False).order_by('-date')[:5]
    unpaid_invoice_count = Invoice.objects.filter(is_paid=False).count()
    unpaid_invoice_total = Invoice.objects.filter(is_paid=False).aggregate(
        total=Coalesce(Sum('grand_total'), Decimal('0'), output_field=DecimalField())
    )['total']

    # ── Recent auto-created documents feed ───────────────────────────
    from audit.models import AuditLog
    recent_auto_docs = AuditLog.objects.filter(
        action='POST'
    ).select_related('user').order_by('-timestamp')[:8]

    # ── Reorder suggestions ──────────────────────────────────────────
    reorder_items = []
    for item in items_with_reorder:
        total_on_hand = StockBalance.objects.filter(item=item).aggregate(
            total=Coalesce(Sum('qty_on_hand'), Decimal('0'), output_field=DecimalField())
        )['total']
        if total_on_hand <= item.reorder_point:
            target_stock = getattr(item, 'maximum_stock', None)
            if target_stock is None:
                target_stock = item.reorder_point * 2
            reorder_items.append({
                'item': item,
                'on_hand': total_on_hand,
                'reorder_point': item.reorder_point,
                'suggested_qty': max(0, target_stock - total_on_hand),
            })

    # ── Formula breakdown for modal ──────────────────────────────────
    dash_formulas = {
        'payments_in_period': total_payments_in_period,
        'discount': total_discount,
        'inv_cogs': invoice_cogs_total,
        'inv_count': combined_count,
        'combined_revenue': combined_revenue,
        'combined_count': combined_count,
        'combined_profit': combined_profit,
        'pos_margin': pos_margin,
        'total_expenses': total_expenses,
        'net_profit': net_profit,
        'inventory_valuation': inventory_valuation,
    }

    context = {
        'period': period,
        'total_items': total_items,
        'low_stock_count': low_stock_count,
        'pending_grns': pending_grns,
        'pending_deliveries': pending_deliveries,
        'recent_moves': list(recent_moves),
        'latest_transactions': latest_transactions,
        # Sales
        'pos_count': pos_count,
        'pos_revenue': pos_revenue,
        'pos_cogs': pos_cogs,
        'pos_profit': pos_profit,
        'pos_margin': pos_margin,
        'combined_revenue': combined_revenue,
        'combined_count': combined_count,
        # Formulas
        'dash_formulas': dash_formulas,
        # Expenses
        'total_expenses': total_expenses,
        'net_profit': net_profit,
        'exp_cat_labels': exp_cat_labels,
        'exp_cat_data': exp_cat_data,
        # Channel
        'ch_labels': ch_labels,
        'ch_data': ch_data,
        'channel_breakdown': channel_breakdown,
        # Top items
        'top_items': top_items,
        # Shifts
        'open_shifts': open_shifts,
        # Valuation
        'inventory_valuation': inventory_valuation,
        # Trend
        'revenue_trend': revenue_trend,
        # Goals
        'active_goals': active_goals,
        # Pending approvals
        'pending_po': pending_po,
        'pending_so': pending_so,
        'pending_grn_draft': pending_grn_draft,
        'pending_dn_draft': pending_dn_draft,
        'pending_approvals_total': pending_approvals_total,
        # Unpaid invoices
        'unpaid_invoices': unpaid_invoices,
        'unpaid_invoice_count': unpaid_invoice_count,
        'unpaid_invoice_total': unpaid_invoice_total,
        # Recent auto-created docs
        'recent_auto_docs': recent_auto_docs,
        # Reorder suggestions
        'reorder_items': reorder_items,
    }
    return render(request, 'theme/dashboard.html', context)


# ─── Environment Toggle ──────────────────────────────────────────────────────

@login_required
def toggle_environment(request):
    """
    POST-only: toggle the current session between 'production' and 'test' DB.
    Only superusers and staff members are allowed to switch.
    Redirects back to the referring page.
    """
    from django.conf import settings
    from django.contrib import messages
    from django.shortcuts import redirect

    if request.method != 'POST':
        return redirect(request.META.get('HTTP_REFERER', '/dashboard/'))

    if not (request.user.is_superuser or request.user.is_staff):
        messages.error(request, 'You do not have permission to switch environments.')
        return redirect(request.META.get('HTTP_REFERER', '/dashboard/'))

    if 'test_env' not in settings.DATABASES:
        messages.warning(
            request,
            'Test environment is not configured. '
            'Set the TEST_DATABASE_URL environment variable to enable it.',
        )
        return redirect(request.META.get('HTTP_REFERER', '/dashboard/'))

    current = request.session.get('app_env', 'production')
    new_env = 'test' if current == 'production' else 'production'
    request.session['app_env'] = new_env

    label = 'TEST' if new_env == 'test' else 'PRODUCTION'
    messages.warning(
        request,
        f'⚠ Switched to {label} database. All data operations now target the {label} environment.',
    )
    return redirect(request.META.get('HTTP_REFERER', '/dashboard/'))

