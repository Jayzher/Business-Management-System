from decimal import Decimal
from datetime import date, timedelta
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Q, F, Count, DecimalField, OuterRef, Subquery
from django.db.models.functions import Coalesce, TruncDate, TruncMonth, ExtractYear, ExtractMonth
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from inventory.models import StockBalance, StockMove, MoveType
from catalog.models import Item
from warehouses.models import Warehouse
from core.cogs import compute_invoice_cogs


def _with_pos_sale_refunds(pos_qs):
    """
    Annotate a POSSale queryset with `refunded_amount` — the total of all
    POSTED refunds against each sale. A PARTIALLY_REFUNDED sale still has
    real revenue (it wasn't returned in full); this lets callers report
    `grand_total - refunded_amount` instead of either double-counting the
    refunded portion or (via the old REFUNDED-exclusion filter) zeroing out
    the whole sale for a refund that only covered one line.
    """
    from pos.models import POSRefund, RefundStatus
    refund_totals = POSRefund.objects.filter(
        original_sale=OuterRef('pk'), status=RefundStatus.POSTED,
    ).values('original_sale').annotate(total=Sum('grand_total')).values('total')
    return pos_qs.annotate(
        refunded_amount=Coalesce(
            Subquery(refund_totals, output_field=DecimalField()),
            Decimal('0'), output_field=DecimalField(),
        ),
    )


def _with_pos_line_refunds(line_qs):
    """
    Same idea as `_with_pos_sale_refunds` but at the POSSaleLine level —
    annotates `refunded_qty`/`refunded_amount` from POSTED POSRefundLines,
    so item- and COGS-level breakdowns can net out exactly the qty/amount
    actually returned rather than the whole line or none of it.
    """
    from pos.models import POSRefundLine, RefundStatus
    refunded_qty_sq = POSRefundLine.objects.filter(
        sale_line=OuterRef('pk'), refund__status=RefundStatus.POSTED,
    ).values('sale_line').annotate(total=Sum('qty')).values('total')
    refunded_amt_sq = POSRefundLine.objects.filter(
        sale_line=OuterRef('pk'), refund__status=RefundStatus.POSTED,
    ).values('sale_line').annotate(total=Sum('amount')).values('total')
    return line_qs.annotate(
        refunded_qty=Coalesce(
            Subquery(refunded_qty_sq, output_field=DecimalField()),
            Decimal('0'), output_field=DecimalField(),
        ),
        refunded_amount=Coalesce(
            Subquery(refunded_amt_sq, output_field=DecimalField()),
            Decimal('0'), output_field=DecimalField(),
        ),
    )


def _calculate_service_cogs(service):
    """
    Calculate COGS for a service (used for partial payment calculations).
    Similar to service_invoice_cogs but works directly on CustomerService object.
    """
    from decimal import Decimal
    from catalog.utils import calculate_line_cogs_with_conversion
    
    total = Decimal('0')
    
    # Product lines (skip scrap)
    for line in service.lines.all():
        try:
            if line.is_scrap:
                continue
            if line.item and line.unit:
                cogs = calculate_line_cogs_with_conversion(line.item, line.qty, line.unit)
                total += cogs
        except Exception:
            continue
    
    # Bundles
    for bundle in service.bundles.all():
        try:
            for pli in bundle.price_list.items.all():
                if pli.item and pli.unit:
                    item_cogs = calculate_line_cogs_with_conversion(
                        pli.item, pli.min_qty, pli.unit
                    )
                    total += item_cogs * bundle.qty
        except Exception:
            continue
    
    # Other materials (at cost)
    for mat in service.other_materials.all():
        try:
            total += mat.line_cost
        except Exception:
            continue
    
    return total


# ── API Views ──────────────────────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def stock_on_hand_report(request):
    """Stock on hand grouped by item."""
    warehouse_id = request.query_params.get('warehouse')
    qs = StockBalance.objects.select_related('item', 'location', 'location__warehouse')
    if warehouse_id:
        qs = qs.filter(location__warehouse_id=warehouse_id)
    qs = qs.filter(qty_on_hand__gt=0).annotate(
        unit_abbrev=Coalesce(
            F('item__selling_unit__abbreviation'),
            F('item__default_unit__abbreviation'),
        )
    ).values(
        'item__code', 'item__name', 'unit_abbrev',
        'location__warehouse__code', 'location__warehouse__name',
    ).annotate(
        total_on_hand=Sum('qty_on_hand'),
        total_reserved=Sum('qty_reserved'),
    ).order_by('item__code')
    return Response(list(qs))


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def stock_movement_report(request):
    """Stock movement summary with filters."""
    item_id = request.query_params.get('item')
    move_type = request.query_params.get('move_type')
    date_from = request.query_params.get('date_from')
    date_to = request.query_params.get('date_to')

    qs = StockMove.objects.filter(status='POSTED')
    if item_id:
        qs = qs.filter(item_id=item_id)
    if move_type:
        qs = qs.filter(move_type=move_type)
    if date_from:
        qs = qs.filter(posted_at__date__gte=date_from)
    if date_to:
        qs = qs.filter(posted_at__date__lte=date_to)

    summary = qs.values('move_type').annotate(
        total_qty=Sum('qty'),
        move_count=Sum(1),
    ).order_by('move_type')
    return Response(list(summary))


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def damaged_summary_report(request):
    """Damaged stock summary."""
    qs = StockMove.objects.filter(
        status='POSTED', move_type=MoveType.DAMAGE
    ).values(
        'item__code', 'item__name',
    ).annotate(
        total_damaged=Sum('qty'),
    ).order_by('-total_damaged')
    return Response(list(qs))


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def low_stock_report(request):
    """Items below reorder point."""
    items = Item.objects.filter(is_active=True, reorder_point__gt=0)
    result = []
    for item in items:
        total_on_hand = StockBalance.objects.filter(item=item).aggregate(
            total=Sum('qty_on_hand')
        )['total'] or 0
        if total_on_hand <= item.reorder_point:
            result.append({
                'item_code': item.code,
                'item_name': item.name,
                'reorder_point': str(item.reorder_point),
                'qty_on_hand': str(total_on_hand),
                'deficit': str(item.reorder_point - total_on_hand),
            })
    return Response(result)


# ── Template Views ─────────────────────────────────────────────────────────

@login_required
def reports_dashboard_view(request):
    return render(request, 'reports/dashboard.html')


@login_required
def stock_on_hand_view(request):
    """HTML rendered stock-on-hand report with warehouse filter."""
    warehouse_id = request.GET.get('warehouse')
    warehouses = Warehouse.objects.filter(is_active=True)
    qs = StockBalance.objects.select_related(
        'item', 'item__default_unit', 'item__selling_unit', 'location', 'location__warehouse'
    ).filter(qty_on_hand__gt=0).annotate(
        line_value=F('qty_on_hand') * Coalesce(F('item__cost_price'), Decimal('0'), output_field=DecimalField()),
    )
    if warehouse_id:
        qs = qs.filter(location__warehouse_id=warehouse_id)
    qs = qs.order_by('item__code', 'location__warehouse__code')

    # Total value is calculated over ALL balances (including negative stock) so
    # over-dispatched items correctly reduce the total inventory value.
    all_bal_qs = StockBalance.objects.annotate(
        line_value=F('qty_on_hand') * Coalesce(F('item__cost_price'), Decimal('0'), output_field=DecimalField()),
    )
    if warehouse_id:
        all_bal_qs = all_bal_qs.filter(location__warehouse_id=warehouse_id)
    total_value = all_bal_qs.aggregate(
        val=Coalesce(
            Sum('line_value', output_field=DecimalField()),
            Decimal('0'), output_field=DecimalField(),
        )
    )['val']

    return render(request, 'reports/stock_on_hand.html', {
        'balances': qs,
        'warehouses': warehouses,
        'selected_warehouse': warehouse_id,
        'total_value': total_value,
    })


@login_required
def stock_movement_view(request):
    """HTML rendered stock movement report with filters."""
    today = date.today()
    first_of_month = today.replace(day=1)
    item_id = request.GET.get('item')
    move_type = request.GET.get('move_type')
    date_from = request.GET.get('date_from', first_of_month.isoformat())
    date_to = request.GET.get('date_to', today.isoformat())

    qs = StockMove.objects.filter(status='POSTED').select_related(
        'item', 'unit', 'from_location', 'to_location', 'created_by'
    )
    if item_id:
        qs = qs.filter(item_id=item_id)
    if move_type:
        qs = qs.filter(move_type=move_type)
    if date_from:
        qs = qs.filter(posted_at__date__gte=date_from)
    if date_to:
        qs = qs.filter(posted_at__date__lte=date_to)

    # Get total count (no pagination - DataTables handles it client-side)
    total_count = qs.count()
    qs = qs.order_by('-posted_at')

    items = Item.objects.filter(is_active=True).order_by('code')
    move_types = MoveType.choices

    return render(request, 'reports/stock_movement.html', {
        'moves': qs,
        'items': items,
        'move_types': move_types,
        'total_count': total_count,
        'filters': {
            'item': item_id or '',
            'move_type': move_type or '',
            'date_from': date_from or '',
            'date_to': date_to or '',
        },
    })


@login_required
def low_stock_view(request):
    """HTML rendered low-stock report."""
    items = Item.objects.filter(is_active=True, reorder_point__gt=0)
    rows = []
    for item in items:
        total_on_hand = StockBalance.objects.filter(item=item).aggregate(
            total=Coalesce(Sum('qty_on_hand'), Decimal('0'))
        )['total']
        if total_on_hand <= item.reorder_point:
            pct = (total_on_hand / item.reorder_point * 100) if item.reorder_point > 0 else Decimal('0')
            rows.append({
                'item': item,
                'qty_on_hand': total_on_hand,
                'deficit': item.reorder_point - total_on_hand,
                'stock_pct': min(pct, Decimal('100')),
            })
    return render(request, 'reports/low_stock.html', {'rows': rows})


# ═══════════════════════════════════════════════════════════════════════════
# SALES REPORT  (daily/monthly by channel/product)
# ═══════════════════════════════════════════════════════════════════════════
@login_required
def sales_report_view(request):
    from pos.models import POSSale, POSSaleLine, SaleStatus
    from sales.models import SalesOrder, SalesOrderLine, SalesOrderPriceListLine
    from core.models import SalesChannel, DocumentStatus

    today = date.today()
    first_of_month = today.replace(day=1)
    date_from = request.GET.get('date_from', first_of_month.isoformat())
    date_to = request.GET.get('date_to', today.isoformat())
    channel_id = request.GET.get('channel', '')
    group_by = request.GET.get('group', 'daily')  # daily or monthly

    # POS sales — PARTIALLY_REFUNDED sales still have real revenue (only
    # some of the sale was returned), so they're included here and netted
    # against their refunded amount below rather than excluded outright.
    pos_qs = POSSale.objects.filter(
        status__in=[SaleStatus.POSTED, SaleStatus.PAID, SaleStatus.PARTIALLY_REFUNDED],
    )
    if date_from:
        pos_qs = pos_qs.filter(created_at__date__gte=date_from)
    if date_to:
        pos_qs = pos_qs.filter(created_at__date__lte=date_to)
    if channel_id:
        pos_qs = pos_qs.filter(channel_id=channel_id)
    pos_qs = _with_pos_sale_refunds(pos_qs)

    # Sales Orders — APPROVED (confirmed) and POSTED (invoice paid / fulfilled)
    so_qs = SalesOrder.objects.filter(status__in=[DocumentStatus.APPROVED, DocumentStatus.POSTED])
    if date_from:
        so_qs = so_qs.filter(order_date__gte=date_from)
    if date_to:
        so_qs = so_qs.filter(order_date__lte=date_to)

    # Summary totals (POS + SO) — revenue is net of any POSTED refunds.
    pos_summary = pos_qs.aggregate(
        total_revenue=Coalesce(
            Sum(F('grand_total') - F('refunded_amount')), Decimal('0'), output_field=DecimalField(),
        ),
        total_discount=Coalesce(Sum('discount_total'), Decimal('0'), output_field=DecimalField()),
        total_tax=Coalesce(Sum('tax_total'), Decimal('0'), output_field=DecimalField()),
        sale_count=Count('id'),
    )

    so_lines_qs = list(SalesOrderLine.objects.filter(
        sales_order__in=so_qs
    ).select_related('sales_order', 'item'))
    so_bundles_qs = list(SalesOrderPriceListLine.objects.filter(
        sales_order__in=so_qs
    ).select_related('sales_order', 'price_list').prefetch_related('price_list__items__item'))
    # Revenue: line totals (includes per-line discounts) + bundle totals
    so_line_rev = sum(line.line_total for line in so_lines_qs)
    so_bundle_rev = sum(bundle.bundle_total for bundle in so_bundles_qs)
    so_revenue = so_line_rev + so_bundle_rev
    so_count = so_qs.count()

    summary = {
        'total_revenue': pos_summary['total_revenue'] + so_revenue,
        'total_discount': pos_summary['total_discount'],
        'total_tax': pos_summary['total_tax'],
        'sale_count': pos_summary['sale_count'] + so_count,
    }

    # COGS — netted against refunded qty for the same reason as revenue above.
    pos_lines = _with_pos_line_refunds(POSSaleLine.objects.filter(sale__in=pos_qs))
    cogs_pos = pos_lines.aggregate(
        total=Coalesce(
            Sum(F('item__cost_price') * (F('qty') - F('refunded_qty')), output_field=DecimalField()),
            Decimal('0'), output_field=DecimalField(),
        )
    )['total']
    # SO COGS: line item costs + bundle item costs
    cogs_so_lines = sum(
        (line.item.cost_price or Decimal('0')) * line.qty_ordered
        for line in so_lines_qs
    )
    cogs_so_bundles = Decimal('0')
    for _b in so_bundles_qs:
        for _p in _b.price_list.items.all():
            cogs_so_bundles += ((_p.item.cost_price or Decimal('0')) * _p.min_qty * _b.qty_multiplier)
    cogs_so = cogs_so_lines + cogs_so_bundles
    cogs = cogs_pos + cogs_so
    gross_profit = summary['total_revenue'] - cogs
    margin = (gross_profit / summary['total_revenue'] * 100) if summary['total_revenue'] > 0 else Decimal('0')

    # ── By-date breakdown (combined POS + SO) ─────────────────────────
    trunc_fn_pos = TruncDate('created_at') if group_by == 'daily' else TruncMonth('created_at')
    trunc_fn_so = TruncDate('sales_order__order_date') if group_by == 'daily' else TruncMonth('sales_order__order_date')

    date_bucket = {}
    for row in pos_qs.annotate(period=trunc_fn_pos).values('period').annotate(
        revenue=Coalesce(Sum(F('grand_total') - F('refunded_amount')), Decimal('0'), output_field=DecimalField()),
        count=Count('id'),
    ):
        date_bucket[row['period']] = {
            'revenue': row['revenue'],
            'count': row['count'],
        }

    # Sales Order lines by period
    for line in so_lines_qs:
        period = line.sales_order.order_date
        if group_by == 'monthly':
            period = period.replace(day=1)
        revenue = line.line_total
        if period in date_bucket:
            date_bucket[period]['revenue'] += revenue
            date_bucket[period]['count'] += 1
        else:
            date_bucket[period] = {'revenue': revenue, 'count': 1}
    # Bundle lines by period (each bundle contributes its bundle_total)
    for bundle in so_bundles_qs:
        period = bundle.sales_order.order_date
        if group_by == 'monthly':
            period = period.replace(day=1)
        if period in date_bucket:
            date_bucket[period]['revenue'] += bundle.bundle_total
        else:
            date_bucket[period] = {'revenue': bundle.bundle_total, 'count': 0}

    date_rows = [
        {'period': k, 'revenue': v['revenue'], 'count': v['count']}
        for k, v in date_bucket.items()
    ]
    date_rows.sort(key=lambda r: r['period'])

    # ── By channel breakdown (POS channels + Sales Orders bucket) ──────
    channel_rows = list(pos_qs.values('channel__name').annotate(
        revenue=Coalesce(Sum(F('grand_total') - F('refunded_amount')), Decimal('0'), output_field=DecimalField()),
        count=Count('id'),
    ).order_by('-revenue'))

    if so_revenue > 0:
        channel_rows.append({
            'channel__name': 'Sales Orders',
            'revenue': so_revenue,
            'count': so_count,
        })

    # ── Top items (combined) ───────────────────────────────────────────
    item_bucket = {}
    for row in pos_lines.values('item__code', 'item__name').annotate(
        total_qty=Sum(F('qty') - F('refunded_qty')),
        total_revenue=Sum(F('line_total') - F('refunded_amount')),
    ):
        key = row['item__code']
        item_bucket[key] = {
            'item__code': row['item__code'],
            'item__name': row['item__name'],
            'total_qty': row['total_qty'],
            'total_revenue': row['total_revenue'],
        }

    for line in so_lines_qs:
        key = line.item.code
        revenue = line.line_total
        if key in item_bucket:
            item_bucket[key]['total_qty'] += line.qty_ordered
            item_bucket[key]['total_revenue'] += revenue
        else:
            item_bucket[key] = {
                'item__code': line.item.code,
                'item__name': line.item.name,
                'total_qty': line.qty_ordered,
                'total_revenue': revenue,
            }
    # Bundle items (each PriceListItem as individual sold item)
    for _b in so_bundles_qs:
        for _p in _b.price_list.items.all():
            key = _p.item.code
            qty = _p.min_qty * _b.qty_multiplier
            revenue = _p.price * qty
            if key in item_bucket:
                item_bucket[key]['total_qty'] += qty
                item_bucket[key]['total_revenue'] += revenue
            else:
                item_bucket[key] = {
                    'item__code': _p.item.code,
                    'item__name': _p.item.name,
                    'total_qty': qty,
                    'total_revenue': revenue,
                }

    top_items = sorted(item_bucket.values(), key=lambda r: r['total_revenue'], reverse=True)[:15]

    channels = SalesChannel.objects.all()

    # Chart data
    chart_labels = []
    chart_data = []
    for r in date_rows:
        try:
            lbl = r['period'].strftime('%b %d' if group_by == 'daily' else '%b %Y')
        except Exception:
            lbl = str(r['period'])
        chart_labels.append(lbl)
        chart_data.append(float(r['revenue']))
    channel_labels = [r['channel__name'] or 'No Channel' for r in channel_rows]
    channel_data = [float(r['revenue']) for r in channel_rows]

    # ── Formula breakdown values ─────────────────────────────────────
    pos_revenue_val = pos_summary['total_revenue']
    formulas = {
        'pos_revenue': pos_revenue_val,
        'pos_count': pos_summary['sale_count'],
        'so_revenue': so_revenue,
        'so_count': so_count,
        'total_revenue': summary['total_revenue'],
        'total_count': summary['sale_count'],
        'cogs_pos': cogs_pos,
        'cogs_so': cogs_so,
        'cogs': cogs,
        'gross_profit': gross_profit,
        'margin': margin,
        'total_discount': summary['total_discount'],
        'total_tax': summary['total_tax'],
    }

    return render(request, 'reports/sales_report.html', {
        'summary': summary,
        'cogs': cogs,
        'gross_profit': gross_profit,
        'margin': margin,
        'date_rows': date_rows,
        'channel_rows': channel_rows,
        'top_items': top_items,
        'channels': channels,
        'group_by': group_by,
        'chart_labels': chart_labels,
        'chart_data': chart_data,
        'channel_labels': channel_labels,
        'channel_data': channel_data,
        'formulas': formulas,
        'filters': {
            'date_from': date_from, 'date_to': date_to,
            'channel': channel_id, 'group': group_by,
        },
    })


# ═══════════════════════════════════════════════════════════════════════════
# PROFIT MARGIN REPORT  (daily/monthly by item)
# ═══════════════════════════════════════════════════════════════════════════
@login_required
def profit_margin_view(request):
    """HTML rendered profit margin report from POS sales and Sales Orders."""
    from pos.models import POSSale, POSSaleLine, SaleStatus
    from core.models import DocumentStatus
    from sales.models import SalesOrder, SalesOrderLine, SalesOrderPriceListLine

    today = date.today()
    first_of_month = today.replace(day=1)
    date_from = request.GET.get('date_from', first_of_month.isoformat())
    date_to = request.GET.get('date_to', today.isoformat())

    # ── POS lines ─────────────────────────────────────────────────────
    # PARTIALLY_REFUNDED included and netted (see _with_pos_line_refunds) —
    # same reasoning as sales_report_view above.
    pos_qs = _with_pos_line_refunds(POSSaleLine.objects.filter(
        sale__status__in=[SaleStatus.POSTED, SaleStatus.PAID, SaleStatus.PARTIALLY_REFUNDED],
    ).select_related('item', 'item__default_unit', 'item__selling_unit', 'unit', 'sale'))
    if date_from:
        pos_qs = pos_qs.filter(sale__created_at__date__gte=date_from)
    if date_to:
        pos_qs = pos_qs.filter(sale__created_at__date__lte=date_to)

    # POS grouped by item
    item_stats = pos_qs.values(
        'item__code', 'item__name', 'item__cost_price',
    ).annotate(
        total_qty=Sum(F('qty') - F('refunded_qty')),
        total_revenue=Sum(F('line_total') - F('refunded_amount')),
    )

    item_bucket = {}
    for row in item_stats:
        key = row['item__code']
        item_bucket[key] = {
            'item_code': row['item__code'],
            'item_name': row['item__name'],
            'cost_price': row['item__cost_price'] or Decimal('0'),
            'total_qty': row['total_qty'],
            'total_revenue': row['total_revenue'],
        }

    # ── SO lines (APPROVED + POSTED) ──────────────────────────────────
    so_qs_pm = SalesOrder.objects.filter(status__in=[DocumentStatus.APPROVED, DocumentStatus.POSTED])
    if date_from:
        so_qs_pm = so_qs_pm.filter(order_date__gte=date_from)
    if date_to:
        so_qs_pm = so_qs_pm.filter(order_date__lte=date_to)
    so_lines_pm = list(SalesOrderLine.objects.filter(
        sales_order__in=so_qs_pm
    ).select_related('item'))
    so_bundles_pm = list(SalesOrderPriceListLine.objects.filter(
        sales_order__in=so_qs_pm
    ).select_related('price_list').prefetch_related('price_list__items__item'))
    # Revenue: line totals (includes per-line discounts) + bundle totals
    so_line_rev = sum(line.line_total for line in so_lines_pm)
    so_bundle_rev = sum(bundle.bundle_total for bundle in so_bundles_pm)
    so_revenue = so_line_rev + so_bundle_rev

    # Add SO lines to item bucket
    for line in so_lines_pm:
        key = line.item.code
        revenue = line.line_total
        if key in item_bucket:
            item_bucket[key]['total_qty'] += line.qty_ordered
            item_bucket[key]['total_revenue'] += revenue
        else:
            item_bucket[key] = {
                'item_code': line.item.code,
                'item_name': line.item.name,
                'cost_price': line.item.cost_price or Decimal('0'),
                'total_qty': line.qty_ordered,
                'total_revenue': revenue,
            }
    # Bundle items in profit margin
    for _b in so_bundles_pm:
        for _p in _b.price_list.items.all():
            key = _p.item.code
            qty = _p.min_qty * _b.qty_multiplier
            revenue = _p.price * qty
            cost = _p.item.cost_price or Decimal('0')
            if key in item_bucket:
                item_bucket[key]['total_qty'] += qty
                item_bucket[key]['total_revenue'] += revenue
            else:
                item_bucket[key] = {
                    'item_code': _p.item.code,
                    'item_name': _p.item.name,
                    'cost_price': cost,
                    'total_qty': qty,
                    'total_revenue': revenue,
                }

    # ── Build output rows ─────────────────────────────────────────────
    rows = []
    grand_revenue = Decimal('0')
    grand_cogs = Decimal('0')
    for data in sorted(item_bucket.values(), key=lambda x: x['total_revenue'], reverse=True):
        cogs = data['cost_price'] * data['total_qty']
        profit = data['total_revenue'] - cogs
        margin = (profit / data['total_revenue'] * 100) if data['total_revenue'] > 0 else Decimal('0')
        rows.append({
            'item_code': data['item_code'],
            'item_name': data['item_name'],
            'qty_sold': data['total_qty'],
            'revenue': data['total_revenue'],
            'cogs': cogs,
            'profit': profit,
            'margin': margin,
        })
        grand_revenue += data['total_revenue']
        grand_cogs += cogs

    grand_profit = grand_revenue - grand_cogs
    grand_margin = (grand_profit / grand_revenue * 100) if grand_revenue > 0 else Decimal('0')

    return render(request, 'reports/profit_margin.html', {
        'rows': rows,
        'grand_revenue': grand_revenue,
        'grand_cogs': grand_cogs,
        'grand_profit': grand_profit,
        'grand_margin': grand_margin,
        'filters': {'date_from': date_from or '', 'date_to': date_to or ''},
    })


# ═══════════════════════════════════════════════════════════════════════════
# FINANCIAL STATEMENT  (P&L)  — Invoice-based (paid invoices only)
# ═══════════════════════════════════════════════════════════════════════════
@login_required
def financial_statement_view(request):
    from core.models import Expense, Invoice, InvoicePayment
    from services.models import CustomerService, ServicePaymentStatus, ServiceStatus
    from sales.models import SalesOrder

    today = date.today()
    first_of_month = today.replace(day=1)
    date_from = request.GET.get('date_from', first_of_month.isoformat())
    date_to = request.GET.get('date_to', today.isoformat())

    # ══════════════════════════════════════════════════════════════════════
    # PAYMENT-BASED REVENUE RECOGNITION
    # ──────────────────────────────────────────────────────────────────────
    # Instead of counting full grand_total when an invoice is marked paid,
    # we count the actual InvoicePayment records that fall within the date
    # range. This prevents double-counting when partial payments are made
    # in one period and the invoice is fully paid in another.
    #
    # Revenue for a period = sum of InvoicePayment.amount within date range
    # COGS for a period   = full_cogs × (period_payments / grand_total)
    # Discount             = discount_total × (period_payments / grand_total)
    # ══════════════════════════════════════════════════════════════════════

    # ── Get all payments in the date range ─────────────────────────────
    payment_qs = InvoicePayment.objects.filter(
        invoice__is_void=False,
    )
    if date_from:
        payment_qs = payment_qs.filter(date__gte=date_from)
    if date_to:
        payment_qs = payment_qs.filter(date__lte=date_to)

    # Get the distinct invoices that have payments in this period
    invoice_ids_with_payments = set(
        payment_qs.values_list('invoice_id', flat=True).distinct()
    )

    # Sum payments per invoice within the date range
    from django.db.models import Sum as DjangoSum
    payments_by_invoice = dict(
        payment_qs.values_list('invoice_id').annotate(
            period_paid=Coalesce(DjangoSum('amount'), Decimal('0'), output_field=DecimalField())
        ).values_list('invoice_id', 'period_paid')
    )

    # Load the invoice objects for those with payments in this period
    invoice_rows = list(
        Invoice.objects.filter(
            pk__in=invoice_ids_with_payments,
            is_void=False,
        )
        .select_related('sales_order__customer', 'pos_sale__customer')
        .prefetch_related(
            'payments',
            'pos_sale__lines__item',
            'pos_sale__lines__unit',
            'pos_sale__bundle_lines__price_list__items__item',
            'pos_sale__bundle_lines__price_list__items__unit',
            'sales_order__lines__item',
            'sales_order__lines__unit',
            'sales_order__price_list_lines__price_list__items__item',
            'sales_order__price_list_lines__price_list__items__unit',
            'customer_services__lines__item',
            'customer_services__lines__unit',
            'customer_services__bundles__price_list__items__item',
            'customer_services__bundles__price_list__items__unit',
            'customer_services__other_materials',
        )
        .order_by('date')
    )

    # Build per-invoice data: COGS, period revenue (payments in range),
    # and proportional discount/COGS based on payment ratio
    invoice_cogs_map = {}
    invoice_period_revenue = {}   # actual payments received in this period
    invoice_period_ratio = {}     # period_payments / grand_total
    invoice_period_cogs = {}      # proportional COGS for this period
    invoice_period_discount = {}  # proportional discount for this period

    for inv in invoice_rows:
        full_cogs = compute_invoice_cogs(inv)
        invoice_cogs_map[inv.pk] = full_cogs

        period_paid = payments_by_invoice.get(inv.pk, Decimal('0'))
        ratio = (period_paid / inv.grand_total) if inv.grand_total > 0 else Decimal('0')
        if ratio > Decimal('1.0'):
            ratio = Decimal('1.0')

        invoice_period_revenue[inv.pk] = period_paid
        invoice_period_ratio[inv.pk] = ratio
        invoice_period_cogs[inv.pk] = (full_cogs * ratio).quantize(Decimal('0.01'))
        invoice_period_discount[inv.pk] = (inv.discount_total * ratio).quantize(Decimal('0.01'))

    # Aggregate totals — ONLY fully-paid invoices count toward P&L.
    # Partial payments are tracked separately for display but excluded
    # from revenue, COGS, and profit calculations.
    invoice_revenue = sum(
        invoice_period_revenue[inv.pk] for inv in invoice_rows if inv.is_paid
    )
    discount = sum(
        invoice_period_discount[inv.pk] for inv in invoice_rows if inv.is_paid
    )
    cogs_from_invoices = sum(
        invoice_period_cogs[inv.pk] for inv in invoice_rows if inv.is_paid
    )

    # ── Separate P&L: Materials Sales vs Services ──────────────────────
    # Materials Sales = POS + Sales Orders (fully paid only)
    materials_revenue = sum(
        invoice_period_revenue[inv.pk] for inv in invoice_rows
        if (inv.sales_order_id or inv.pos_sale_id) and inv.is_paid
    )
    materials_discount = sum(
        invoice_period_discount[inv.pk] for inv in invoice_rows
        if (inv.sales_order_id or inv.pos_sale_id) and inv.is_paid
    )
    materials_cogs = sum(
        invoice_period_cogs[inv.pk] for inv in invoice_rows
        if (inv.sales_order_id or inv.pos_sale_id) and inv.is_paid
    )
    materials_gross_profit = materials_revenue - materials_discount - materials_cogs
    materials_gross_margin = (
        (materials_gross_profit / (materials_revenue - materials_discount) * 100)
        if (materials_revenue - materials_discount) > 0 else Decimal('0')
    )

    # Services = Everything else (customer services, fully paid only)
    services_revenue = sum(
        invoice_period_revenue[inv.pk] for inv in invoice_rows
        if not inv.sales_order_id and not inv.pos_sale_id and inv.is_paid
    )
    services_discount = sum(
        invoice_period_discount[inv.pk] for inv in invoice_rows
        if not inv.sales_order_id and not inv.pos_sale_id and inv.is_paid
    )
    services_cogs = sum(
        invoice_period_cogs[inv.pk] for inv in invoice_rows
        if not inv.sales_order_id and not inv.pos_sale_id and inv.is_paid
    )
    services_gross_profit = services_revenue - services_discount - services_cogs
    services_gross_margin = (
        (services_gross_profit / (services_revenue - services_discount) * 100)
        if (services_revenue - services_discount) > 0 else Decimal('0')
    )
    
    # ── Partial Payments (invoices not yet fully paid) ────────────────
    # These are invoices where some payments exist but is_paid is still False.
    # Since we already count their payments above (via InvoicePayment date
    # filtering), we only need this section for the BREAKDOWN DISPLAY in the
    # modal — not for P&L totals. The P&L numbers come from payment records.
    from django.db.models import Q

    partial_services_revenue = Decimal('0')
    partial_services_cogs = Decimal('0')
    partial_services_breakdown = []

    partial_so_revenue = Decimal('0')
    partial_so_cogs = Decimal('0')
    partial_so_breakdown = []

    debug_total_partial_invoices = 0
    debug_services_with_partial = 0
    debug_so_with_partial = 0

    # Identify invoices that are NOT fully paid but had payments in this period
    for inv in invoice_rows:
        if inv.is_paid:
            continue  # Fully paid — shown in the Invoices tab, not here

        period_paid = invoice_period_revenue.get(inv.pk, Decimal('0'))
        if period_paid <= 0:
            continue

        debug_total_partial_invoices += 1
        ratio = invoice_period_ratio[inv.pk]
        proportional_cogs = invoice_period_cogs[inv.pk]

        if hasattr(inv, 'customer_services') and inv.customer_services.exists():
            debug_services_with_partial += 1
            partial_services_revenue += period_paid
            partial_services_cogs += proportional_cogs

            services = inv.customer_services.all()
            partial_services_breakdown.append({
                'invoice': inv,
                'service': services[0] if services else None,
                'revenue': period_paid,
                'cogs': proportional_cogs,
                'gross_profit': period_paid - proportional_cogs,
                'payment_percentage': ratio * 100,
                'balance_due': inv.balance_due,
            })
        elif inv.sales_order_id or inv.pos_sale_id:
            debug_so_with_partial += 1
            partial_so_revenue += period_paid
            partial_so_cogs += proportional_cogs

            partial_so_breakdown.append({
                'invoice': inv,
                'sales_order': inv.sales_order if inv.sales_order_id else None,
                'pos_sale': inv.pos_sale if inv.pos_sale_id else None,
                'revenue': period_paid,
                'cogs': proportional_cogs,
                'gross_profit': period_paid - proportional_cogs,
                'payment_percentage': ratio * 100,
                'balance_due': inv.balance_due,
            })

    # ── Non-Invoiced Services with Partial Payments ────────────────────
    # Services that have partial_payment_amount set but haven't been
    # invoiced yet. These are the ONLY partial payments that need to be
    # added on top of invoice-based revenue, because they have no
    # InvoicePayment records.
    non_invoiced_services_qs = CustomerService.objects.filter(
        invoice__isnull=True,  # Not yet invoiced
        partial_payment_amount__gt=0,  # Has received payment
        payment_status=ServicePaymentStatus.PARTIAL,  # Status is PARTIAL
    ).exclude(
        status=ServiceStatus.CANCELLED  # Exclude cancelled services
    )

    # Date filter: use service_date for filtering (since there's no invoice/payment date yet)
    if date_from:
        non_invoiced_services_qs = non_invoiced_services_qs.filter(service_date__gte=date_from)
    if date_to:
        non_invoiced_services_qs = non_invoiced_services_qs.filter(service_date__lte=date_to)

    non_invoiced_services_qs = non_invoiced_services_qs.prefetch_related(
        'lines__item',
        'lines__unit',
        'other_materials',
        'bundles__price_list__items__item',
        'bundles__price_list__items__unit',
    )

    # Revenue/COGS from non-invoiced partial payments (added to P&L totals)
    non_invoiced_partial_services_revenue = Decimal('0')
    non_invoiced_partial_services_cogs = Decimal('0')

    for svc in non_invoiced_services_qs:
        grand_total = svc.grand_total
        if grand_total <= 0:
            continue

        payment_amount = svc.partial_payment_amount or Decimal('0')
        payment_percentage = (payment_amount / grand_total) if grand_total > 0 else Decimal('0')
        if payment_percentage > Decimal('1.0'):
            payment_percentage = Decimal('1.0')

        # Calculate COGS using the helper
        full_cogs = _calculate_service_cogs(svc)
        proportional_cogs = (full_cogs * payment_percentage).quantize(Decimal('0.01'))

        debug_services_with_partial += 1
        non_invoiced_partial_services_revenue += payment_amount
        non_invoiced_partial_services_cogs += proportional_cogs
        partial_services_revenue += payment_amount
        partial_services_cogs += proportional_cogs

        class PseudoInvoice:
            def __init__(self, svc):
                self.invoice_number = "(Not Invoiced)"
                self.customer_name = svc.customer_name
                self.date = svc.service_date
                self.grand_total = svc.grand_total
                self.balance_due = svc.grand_total - (svc.partial_payment_amount or Decimal('0'))

        partial_services_breakdown.append({
            'invoice': PseudoInvoice(svc),
            'service': svc,
            'revenue': payment_amount,
            'cogs': proportional_cogs,
            'gross_profit': payment_amount - proportional_cogs,
            'payment_percentage': payment_percentage * 100,
            'balance_due': svc.grand_total - payment_amount,
        })

    # Debug info
    debug_total_services = CustomerService.objects.exclude(status=ServiceStatus.CANCELLED).count()
    debug_services_with_amount = debug_services_with_partial
    debug_services_not_invoiced = non_invoiced_services_qs.count()
    debug_services_with_status = debug_services_with_partial
    debug_query_count = debug_services_with_partial
    debug_invoiced_service_count = 0

    debug_total_so = SalesOrder.objects.count()
    debug_so_with_amount = debug_so_with_partial
    debug_so_not_invoiced = 0
    debug_so_with_status = debug_so_with_partial
    debug_so_query_count = debug_so_with_partial
    
    # ── Update totals ─────────────────────────────────────────────────
    # Partial payments are excluded from P&L. The _with_partial variables
    # are kept identical to the base values for template backward
    # compatibility, but no partial amounts are added.
    services_revenue_with_partial = services_revenue
    services_cogs_with_partial = services_cogs
    services_gross_profit_with_partial = services_gross_profit
    services_gross_margin_with_partial = services_gross_margin

    # Materials totals: no partial payments included
    materials_revenue_with_partial = materials_revenue
    materials_cogs_with_partial = materials_cogs
    materials_gross_profit_with_partial = materials_gross_profit
    materials_gross_margin_with_partial = materials_gross_margin

    # Calculate net revenues (after discounts)
    materials_net_revenue = materials_revenue_with_partial - materials_discount
    services_net_revenue = services_revenue_with_partial - services_discount

    # Total revenue = fully-paid invoice payments only (no partial)
    invoice_revenue_with_partial = invoice_revenue
    net_revenue = invoice_revenue_with_partial - discount

    # ── COGS from expense categories marked as COGS ────────────────────
    exp_qs = Expense.objects.all()
    if date_from:
        exp_qs = exp_qs.filter(date__gte=date_from)
    if date_to:
        exp_qs = exp_qs.filter(date__lte=date_to)

    cogs_expenses = exp_qs.filter(category__is_cogs=True).aggregate(
        total=Coalesce(Sum('amount'), Decimal('0'), output_field=DecimalField())
    )['total']

    # ── Total COGS ──────────────────────────────────────────────────────
    # Only fully-paid invoice COGS + expense-based COGS. No partial payments.
    total_cogs = cogs_from_invoices + cogs_expenses
    gross_profit = net_revenue - total_cogs
    gross_margin = (gross_profit / net_revenue * 100) if net_revenue > 0 else Decimal('0')

    # ── OPERATING EXPENSES (non-COGS) ──────────────────────────────────
    opex_rows = exp_qs.filter(category__is_cogs=False).values(
        'category__name'
    ).annotate(
        total=Coalesce(Sum('amount'), Decimal('0'), output_field=DecimalField())
    ).order_by('-total')

    total_opex = sum(r['total'] for r in opex_rows)
    net_profit = gross_profit - total_opex
    net_margin = (net_profit / net_revenue * 100) if net_revenue > 0 else Decimal('0')

    # ── Monthly P&L trend (by payment date month) ────────────────────
    monthly_pay_raw = list(
        payment_qs.annotate(yr=ExtractYear('date'), mo=ExtractMonth('date'))
        .values('yr', 'mo').annotate(
            total=Coalesce(Sum('amount'), Decimal('0'), output_field=DecimalField())
        ).order_by('yr', 'mo')
    )
    monthly_exp_raw = list(
        exp_qs.annotate(yr=ExtractYear('date'), mo=ExtractMonth('date'))
        .values('yr', 'mo').annotate(
            total=Coalesce(Sum('amount'), Decimal('0'), output_field=DecimalField())
        ).order_by('yr', 'mo')
    )

    month_map = {}
    for r in monthly_pay_raw:
        key = date(r['yr'], r['mo'], 1).strftime('%b %Y')
        month_map.setdefault(key, {'revenue': Decimal('0'), 'expenses': Decimal('0')})
        month_map[key]['revenue'] += r['total']
    for r in monthly_exp_raw:
        key = date(r['yr'], r['mo'], 1).strftime('%b %Y')
        month_map.setdefault(key, {'revenue': Decimal('0'), 'expenses': Decimal('0')})
        month_map[key]['expenses'] = r['total']

    trend_labels = list(month_map.keys())
    trend_revenue = [float(month_map[k]['revenue']) for k in trend_labels]
    trend_expenses = [float(month_map[k]['expenses']) for k in trend_labels]
    trend_profit = [float(month_map[k]['revenue'] - month_map[k]['expenses']) for k in trend_labels]

    # ── Breakdown: one row per invoice with payments in period ────────
    breakdown_rows = []
    for inv in invoice_rows:
        period_paid = invoice_period_revenue.get(inv.pk, Decimal('0'))
        if period_paid <= 0:
            continue
        # Only show fully-paid invoices in the Invoices tab
        # (partial payments are shown in their own tabs)
        if not inv.is_paid:
            continue

        source_type = 'INV'
        ref = ''
        other_mat_cost = Decimal('0')
        if inv.sales_order_id:
            source_type = 'SO'
            ref = inv.sales_order.document_number
        elif inv.pos_sale_id:
            source_type = 'POS'
            ref = inv.pos_sale.sale_no
        elif hasattr(inv, 'customer_services') and inv.customer_services.exists():
            source_type = 'SVC'
            services = inv.customer_services.all()
            ref = services[0].service_number if services else ''
            for svc_obj in services:
                other_mat_cost += sum(
                    (mat.line_cost for mat in svc_obj.other_materials.all()),
                    Decimal('0'),
                )
        cogs_val = invoice_period_cogs[inv.pk]
        disc_val = invoice_period_discount[inv.pk]
        payment_methods = ', '.join(
            p.get_method_display() for p in inv.payments.all()
        ) or '—'
        breakdown_rows.append({
            'type': source_type,
            'ref': ref,
            'invoice_no': inv.invoice_number,
            'date': inv.paid_date,
            'customer': inv.customer_name or '—',
            'revenue': period_paid,
            'discount': disc_val,
            'cogs': cogs_val,
            'other_mat_cost': (other_mat_cost * invoice_period_ratio[inv.pk]).quantize(Decimal('0.01')),
            'gross_profit': period_paid - disc_val - cogs_val,
            'payment_methods': payment_methods,
        })

    breakdown_total_revenue = sum(r['revenue'] for r in breakdown_rows)
    breakdown_total_discount = sum(r['discount'] for r in breakdown_rows)
    breakdown_total_cogs = sum(r['cogs'] for r in breakdown_rows)
    breakdown_total_other_mat = sum(r['other_mat_cost'] for r in breakdown_rows)
    breakdown_total_gp = sum(r['gross_profit'] for r in breakdown_rows)

    # ── Payment method summary (from InvoicePayment records in period) ─
    from django.db.models import Count
    payment_method_rows = list(
        payment_qs
        .values('method')
        .annotate(
            total=Coalesce(Sum('amount'), Decimal('0'), output_field=DecimalField()),
            count=Count('id'),
        )
        .order_by('-total')
    )
    # Attach display name
    from core.models import PaymentMethod as PM
    for row in payment_method_rows:
        row['method_display'] = dict(PM.choices).get(row['method'], row['method'])
    payment_total_collected = sum(r['total'] for r in payment_method_rows)

    # Invoice count (invoices that had payments in this period)
    inv_count = len(invoice_ids_with_payments)

    # For template backward compatibility
    so_invoice_revenue = sum(
        invoice_period_revenue[inv.pk] for inv in invoice_rows if inv.sales_order_id
    )
    pos_invoice_revenue = sum(
        invoice_period_revenue[inv.pk] for inv in invoice_rows if inv.pos_sale_id
    )
    svc_invoice_revenue = sum(
        invoice_period_revenue[inv.pk] for inv in invoice_rows
        if not inv.sales_order_id and not inv.pos_sale_id
    )

    return render(request, 'reports/financial_statement.html', {
        'invoice_revenue': invoice_revenue_with_partial,  # Updated to include partial payments
        'so_invoice_revenue': so_invoice_revenue,
        'pos_invoice_revenue': pos_invoice_revenue,
        'svc_invoice_revenue': svc_invoice_revenue,
        'discount': discount,
        'net_revenue': net_revenue,
        'cogs_from_invoices': cogs_from_invoices,
        'cogs_expenses': cogs_expenses,
        # 'other_mat_total': removed - now included in cogs_from_invoices
        'total_cogs': total_cogs,
        'gross_profit': gross_profit,
        'gross_margin': gross_margin,
        # Separate P&L for Materials vs Services
        'materials_revenue': materials_revenue,
        'materials_discount': materials_discount,
        'materials_cogs': materials_cogs,
        'materials_net_revenue': materials_net_revenue,
        'materials_gross_profit': materials_gross_profit,
        'materials_gross_margin': materials_gross_margin,
        'materials_revenue_with_partial': materials_revenue_with_partial,
        'materials_cogs_with_partial': materials_cogs_with_partial,
        'materials_gross_profit_with_partial': materials_gross_profit_with_partial,
        'materials_gross_margin_with_partial': materials_gross_margin_with_partial,
        'services_revenue': services_revenue,
        'services_discount': services_discount,
        'services_cogs': services_cogs,
        'services_net_revenue': services_net_revenue,
        'services_gross_profit': services_gross_profit,
        'services_gross_margin': services_gross_margin,
        # Partial payments - Services
        'partial_services_revenue': partial_services_revenue,
        'partial_services_cogs': partial_services_cogs,
        'partial_services_count': len(partial_services_breakdown),
        'services_revenue_with_partial': services_revenue_with_partial,
        'services_cogs_with_partial': services_cogs_with_partial,
        'services_gross_profit_with_partial': services_gross_profit_with_partial,
        'services_gross_margin_with_partial': services_gross_margin_with_partial,
        'partial_services_breakdown': partial_services_breakdown,
        # Partial payments - Sales Orders
        'partial_so_revenue': partial_so_revenue,
        'partial_so_cogs': partial_so_cogs,
        'partial_so_count': len(partial_so_breakdown),
        'partial_so_breakdown': partial_so_breakdown,
        # Debug info - Partial Invoices
        'debug_total_partial_invoices': debug_total_partial_invoices,
        'debug_services_with_partial': debug_services_with_partial,
        'debug_so_with_partial': debug_so_with_partial,
        # Debug info - Services
        'debug_total_services': debug_total_services,
        'debug_services_with_amount': debug_services_with_amount,
        'debug_services_not_invoiced': debug_services_not_invoiced,
        'debug_services_with_status': debug_services_with_status,
        'debug_query_count': debug_query_count,
        'debug_invoiced_service_count': debug_invoiced_service_count,
        # Debug info - Sales Orders
        'debug_total_so': debug_total_so,
        'debug_so_with_amount': debug_so_with_amount,
        'debug_so_not_invoiced': debug_so_not_invoiced,
        'debug_so_with_status': debug_so_with_status,
        'debug_so_query_count': debug_so_query_count,
        'opex_rows': opex_rows,
        'total_opex': total_opex,
        'net_profit': net_profit,
        'net_margin': net_margin,
        'trend_labels': trend_labels,
        'trend_revenue': trend_revenue,
        'trend_expenses': trend_expenses,
        'trend_profit': trend_profit,
        'filters': {'date_from': date_from, 'date_to': date_to},
        'breakdown_rows': breakdown_rows,
        'breakdown_total_revenue': breakdown_total_revenue,
        'breakdown_total_discount': breakdown_total_discount,
        'breakdown_total_cogs': breakdown_total_cogs,
        'breakdown_total_other_mat': breakdown_total_other_mat,
        'breakdown_total_gp': breakdown_total_gp,
        'payment_method_rows': payment_method_rows,
        'payment_total_collected': payment_total_collected,
        'inv_count': inv_count,
    })


# ── Stock Aging Report ────────────────────────────────────────────────────

@login_required
def stock_aging_view(request):
    """Shows stock aging based on first RECEIVE move date per item/location."""
    from core.utils import sort_queryset, paginate_queryset, search_queryset
    today = timezone.now().date()
    warehouse_id = request.GET.get('warehouse', '')

    balances = StockBalance.objects.filter(qty_on_hand__gt=0).select_related(
        'item', 'location', 'location__warehouse'
    )
    if warehouse_id:
        balances = balances.filter(location__warehouse_id=warehouse_id)
    balances = search_queryset(request, balances, ['item__code', 'item__name'])

    sort_map = {
        'item_code': 'item__code',
        'item_name': 'item__name',
        'warehouse': 'location__warehouse__name',
        'location': 'location__code',
        'qty': 'qty_on_hand',
        'cost_price': 'item__cost_price',
    }
    balances, sort, direction = sort_queryset(request, balances, sort_map, default_key='updated_at', default_dir='desc')

    aging_data = []
    for bal in balances:
        first_receive = StockMove.objects.filter(
            item=bal.item,
            to_location=bal.location,
            move_type__in=[MoveType.RECEIVE, MoveType.RETURN_IN],
            status='POSTED',
        ).order_by('posted_at').values_list('posted_at', flat=True).first()

        if first_receive:
            age_days = (today - first_receive.date()).days
        else:
            age_days = 0

        if age_days <= 30:
            bucket = '0-30 days'
            bucket_order = 1
        elif age_days <= 60:
            bucket = '31-60 days'
            bucket_order = 2
        elif age_days <= 90:
            bucket = '61-90 days'
            bucket_order = 3
        elif age_days <= 180:
            bucket = '91-180 days'
            bucket_order = 4
        else:
            bucket = '180+ days'
            bucket_order = 5

        value = float(bal.qty_on_hand * (bal.item.cost_price or Decimal('0')))
        aging_data.append({
            'item_code': bal.item.code,
            'item_name': bal.item.name,
            'warehouse': bal.location.warehouse.name,
            'location': bal.location.code,
            'qty': bal.qty_on_hand,
            'cost_price': bal.item.cost_price or Decimal('0'),
            'value': value,
            'age_days': age_days,
            'bucket': bucket,
            'bucket_order': bucket_order,
        })

    # Row order follows the sort_queryset-driven `balances` ordering above
    # (defaults to newest-updated stock first; clickable columns re-order it).

    # Summary by bucket
    bucket_summary = {}
    for row in aging_data:
        b = row['bucket']
        if b not in bucket_summary:
            bucket_summary[b] = {'count': 0, 'qty': Decimal('0'), 'value': 0.0}
        bucket_summary[b]['count'] += 1
        bucket_summary[b]['qty'] += row['qty']
        bucket_summary[b]['value'] += row['value']

    page_obj = paginate_queryset(request, aging_data, per_page=25)

    warehouses = Warehouse.objects.all()
    return render(request, 'reports/stock_aging.html', {
        'aging_data': page_obj,
        'page_obj': page_obj,
        'sort': sort,
        'dir': direction,
        'bucket_summary': bucket_summary,
        'warehouses': warehouses,
        'selected_warehouse': warehouse_id,
    })


# ── Expense Report ───────────────────────────────────────────────────────────

@login_required
def expense_report_view(request):
    """HTML rendered expense report with date/category filters."""
    from core.models import Expense, ExpenseCategory

    today = date.today()
    first_of_month = today.replace(day=1)
    date_from = request.GET.get('date_from', first_of_month.isoformat())
    date_to = request.GET.get('date_to', today.isoformat())
    category_id = request.GET.get('category', '')
    group_by = request.GET.get('group', 'daily')

    qs = Expense.objects.all()
    if date_from:
        qs = qs.filter(date__gte=date_from)
    if date_to:
        qs = qs.filter(date__lte=date_to)
    if category_id:
        qs = qs.filter(category_id=category_id)

    total_expenses = qs.aggregate(
        total=Coalesce(Sum('amount'), Decimal('0'), output_field=DecimalField()),
        count=Count('id'),
    )

    # Date breakdown — use .values('date') directly (DateField, not DateTimeField)
    # to avoid SQLite UDF errors from TruncDate with USE_TZ=True
    raw_rows = list(
        qs.values('date')
        .annotate(total=Coalesce(Sum('amount'), Decimal('0'), output_field=DecimalField()), count=Count('id'))
        .order_by('date')
    )
    if group_by == 'monthly':
        month_bucket = {}
        for row in raw_rows:
            key = row['date'].replace(day=1)
            if key in month_bucket:
                month_bucket[key]['total'] += row['total']
                month_bucket[key]['count'] += row['count']
            else:
                month_bucket[key] = {'period': key, 'total': row['total'], 'count': row['count']}
        date_rows = sorted(month_bucket.values(), key=lambda r: r['period'])
    else:
        date_rows = [{'period': r['date'], 'total': r['total'], 'count': r['count']} for r in raw_rows]

    chart_labels = []
    chart_data = []
    for row in date_rows:
        try:
            lbl = row['period'].strftime('%b %d' if group_by == 'daily' else '%b %Y')
        except Exception:
            lbl = str(row['period'])
        chart_labels.append(lbl)
        chart_data.append(float(row['total']))

    # Category breakdown
    cat_rows = list(
        qs.values('category__name', 'category__is_cogs')
        .annotate(total=Coalesce(Sum('amount'), Decimal('0'), output_field=DecimalField()), count=Count('id'))
        .order_by('-total')
    )
    cat_labels = [r['category__name'] for r in cat_rows]
    cat_data = [float(r['total']) for r in cat_rows]

    categories = ExpenseCategory.objects.all().order_by('name')

    return render(request, 'reports/expense_report.html', {
        'total_expenses': total_expenses,
        'date_rows': date_rows,
        'cat_rows': cat_rows,
        'chart_labels': chart_labels,
        'chart_data': chart_data,
        'cat_labels': cat_labels,
        'cat_data': cat_data,
        'categories': categories,
        'group_by': group_by,
        'filters': {
            'date_from': date_from or '',
            'date_to': date_to or '',
            'category': category_id or '',
            'group': group_by,
        },
    })


# ── Inventory Valuation Report ──────────────────────────────────────────────

@login_required
def inventory_valuation_view(request):
    """HTML rendered inventory valuation report."""
    warehouse_id = request.GET.get('warehouse')
    warehouses = Warehouse.objects.filter(is_active=True)

    qs = StockBalance.objects.filter(qty_on_hand__gt=0).select_related(
        'item', 'item__default_unit', 'item__selling_unit', 'location', 'location__warehouse'
    )
    if warehouse_id:
        qs = qs.filter(location__warehouse_id=warehouse_id)

    rows = []
    grand_total = Decimal('0')
    for bal in qs.order_by('location__warehouse__code', 'item__code'):
        cost = bal.item.cost_price or Decimal('0')
        value = bal.qty_on_hand * cost
        grand_total += value
        rows.append({
            'item': bal.item,
            'warehouse': bal.location.warehouse.name,
            'location': bal.location.code,
            'qty': bal.qty_on_hand,
            'cost_price': cost,
            'value': value,
        })

    return render(request, 'reports/inventory_valuation.html', {
        'rows': rows,
        'grand_total': grand_total,
        'warehouses': warehouses,
        'selected_warehouse': warehouse_id,
    })
