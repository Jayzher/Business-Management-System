from decimal import Decimal
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Count, Q, F, DecimalField
from django.db.models.functions import Coalesce
from django.utils import timezone
from datetime import timedelta


@login_required
def dashboard_view(request):
    from catalog.models import Item
    from inventory.models import StockBalance, StockMove
    from procurement.models import GoodsReceipt
    from sales.models import DeliveryNote
    from pos.models import POSSale, POSSaleLine, POSShift, SaleStatus, ShiftStatus
    from core.models import Expense, ExpenseCategory, TargetGoal, SalesChannel

    now = timezone.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # ── Period toggle (today / week / month / year) ────────────────────
    period = request.GET.get('period', 'today')
    if period == 'week':
        period_start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == 'month':
        period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    elif period == 'year':
        period_start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        period_start = today_start
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

    # ── Sales for selected period ──────────────────────────────────────
    period_sales = POSSale.objects.filter(
        status__in=[SaleStatus.POSTED, SaleStatus.PAID],
        created_at__gte=period_start,
    )
    pos_count = period_sales.count()
    pos_revenue = period_sales.aggregate(
        total=Coalesce(Sum('grand_total'), Decimal('0'), output_field=DecimalField())
    )['total']

    pos_cogs = POSSaleLine.objects.filter(sale__in=period_sales).aggregate(
        total=Coalesce(
            Sum(F('item__cost_price') * F('qty'), output_field=DecimalField()),
            Decimal('0'), output_field=DecimalField(),
        )
    )['total']
    pos_profit = pos_revenue - pos_cogs

    # Paid invoices (non-POS) to reflect in dashboard revenue/count
    from core.models import Invoice
    paid_invoices = Invoice.objects.filter(is_paid=True, paid_at__isnull=False, paid_at__gte=period_start)
    invoice_paid_total = paid_invoices.aggregate(
        total=Coalesce(Sum('grand_total'), Decimal('0'), output_field=DecimalField())
    )['total']
    invoice_paid_count = paid_invoices.count()

    combined_revenue = pos_revenue + invoice_paid_total
    combined_count = pos_count + invoice_paid_count
    combined_profit = pos_profit + invoice_paid_total  # conservative: treat invoice revenue with zero extra COGS
    pos_margin = (combined_profit / combined_revenue * 100) if combined_revenue > 0 else Decimal('0')

    # ── Expenses for selected period ───────────────────────────────────
    period_expenses = Expense.objects.filter(date__gte=period_start.date())
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
        total=Coalesce(Sum('grand_total'), Decimal('0'), output_field=DecimalField()),
        count=Count('id'),
    ).order_by('-total')
    ch_labels = [r['channel__name'] or 'No Channel' for r in channel_breakdown]
    ch_data = [float(r['total']) for r in channel_breakdown]

    # ── Top items sold ─────────────────────────────────────────────────
    top_items = POSSaleLine.objects.filter(sale__in=period_sales).values(
        'item__code', 'item__name'
    ).annotate(
        total_qty=Sum('qty'),
        total_revenue=Sum('line_total'),
    ).order_by('-total_revenue')[:5]

    # Open shifts
    open_shifts = POSShift.objects.filter(status=ShiftStatus.OPEN).select_related('register', 'opened_by')

    # ── Inventory valuation ────────────────────────────────────────────
    inventory_valuation = StockBalance.objects.filter(qty_on_hand__gt=0).aggregate(
        total=Coalesce(
            Sum(F('qty_on_hand') * F('item__cost_price'), output_field=DecimalField()),
            Decimal('0'), output_field=DecimalField(),
        )
    )['total']

    # ── 7-day revenue trend ────────────────────────────────────────────
    revenue_trend = []
    for i in range(6, -1, -1):
        day = (now - timedelta(days=i)).date()
        day_start_dt = timezone.make_aware(timezone.datetime.combine(day, timezone.datetime.min.time()))
        day_end_dt = day_start_dt + timedelta(days=1)
        rev = POSSale.objects.filter(
            status__in=[SaleStatus.POSTED, SaleStatus.PAID],
            created_at__gte=day_start_dt, created_at__lt=day_end_dt,
        ).aggregate(
            total=Coalesce(Sum('grand_total'), Decimal('0'), output_field=DecimalField())
        )['total']
        revenue_trend.append({'date': day.strftime('%b %d'), 'revenue': float(rev)})

    # ── Active goals ───────────────────────────────────────────────────
    active_goals = TargetGoal.objects.filter(
        status__in=['PENDING', 'IN_PROGRESS']
    ).order_by('-priority', 'due_date')[:5]

    # ── Pending approvals widget ─────────────────────────────────────
    from procurement.models import PurchaseOrder
    from sales.models import SalesOrder
    from core.models import Invoice
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
        'pos_revenue': pos_revenue,
        'pos_count': pos_count,
        'pos_cogs': pos_cogs,
        'pos_profit': pos_profit,
        'invoice_paid_total': invoice_paid_total,
        'invoice_paid_count': invoice_paid_count,
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
