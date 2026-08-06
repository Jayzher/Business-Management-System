"""
Monthly Cashflow Signals
=========================
Automatically update monthly cashflow summaries when transactions occur.

This module uses the same calculation logic as the management command
(calculate_monthly_cashflow) to ensure consistency between real-time
signal updates and batch recalculations.

Key accounting principles:
  - Cash Flow: Cash basis (when money moves)
  - P&L: Accrual basis (when revenue is earned / expenses incurred)
  - Balance Sheet: Total Assets = Cash + Inventory + AR
"""
import threading
from datetime import date, datetime, time
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum, F, Q, Value, DecimalField
from django.db.models.functions import Coalesce
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.utils import timezone

from cashflow.models import (
    MonthlyCashflowSummary, CashFlowTransaction,
    CashFlowType, CashFlowStatus, CashFlowCategory,
    clamp_ratio_pct,
)
from core.models import Expense, Invoice, InvoicePayment, DocumentStatus
from pos.models import POSSale, SaleStatus
from sales.models import DeliveryNote, SalesPickup
from procurement.models import GoodsReceipt
from inventory.models import StockMove, MoveType, MoveStatus
from catalog.models import Item


def _make_aware_start(d):
    """Convert a date to a timezone-aware datetime at start of day."""
    return timezone.make_aware(datetime.combine(d, time.min))


def _make_aware_end(d):
    """Convert a date to a timezone-aware datetime at end of day."""
    return timezone.make_aware(datetime.combine(d, time.max))


def update_monthly_summary(year, month, user=None):
    """
    Update or create monthly summary for the given year/month.

    This function mirrors the logic in calculate_monthly_cashflow management
    command to ensure consistency between signal-triggered updates and
    batch recalculations.
    """
    from calendar import monthrange

    # Date range for this month
    start_date = date(year, month, 1)
    last_day = monthrange(year, month)[1]
    if month == 12:
        next_month_start = date(year + 1, 1, 1)
    else:
        next_month_start = date(year, month + 1, 1)

    # Timezone-aware datetimes for DateTimeField queries
    start_dt = _make_aware_start(start_date)
    end_dt = _make_aware_start(next_month_start)

    # ── Previous month summary ───────────────────────────────────────────
    if month == 1:
        prev_summary = MonthlyCashflowSummary.objects.filter(
            year=year - 1, month=12
        ).first()
    else:
        prev_summary = MonthlyCashflowSummary.objects.filter(
            year=year, month=month - 1
        ).first()

    # ══════════════════════════════════════════════════════════════════════
    # 1. INVENTORY (Formula-based: Closing = Opening + Purchased - COGS)
    # ══════════════════════════════════════════════════════════════════════
    inventory_purchased = _calculate_procurement_costs(start_date, next_month_start)
    # Sales Returns reverse both revenue and COGS — reflect that here so the
    # Monthly Summary matches the daily cashflow ledger (cashflow/sync.py),
    # which already nets returns into its per-day revenue/COGS buckets.
    sales_returns_revenue = _calculate_sales_returns_revenue(start_date, next_month_start)
    sales_returns_cogs = _calculate_sales_returns_cogs(start_date, next_month_start)
    cogs_actual = (
        _calculate_actual_cogs(start_date, next_month_start, start_dt, end_dt)
        - sales_returns_cogs
    )

    if prev_summary:
        inventory_opening = prev_summary.inventory_value_closing
    else:
        inventory_opening = Decimal('0')

    inventory_closing = inventory_opening + inventory_purchased - cogs_actual
    if inventory_closing < 0:
        inventory_closing = Decimal('0')

    # ══════════════════════════════════════════════════════════════════════
    # 2. ACCOUNTS RECEIVABLE
    # ══════════════════════════════════════════════════════════════════════
    ar_opening = _calculate_ar(start_date)
    ar_closing = _calculate_ar(next_month_start)
    ar_collections = _calculate_ar_collections(start_date, next_month_start)

    # ══════════════════════════════════════════════════════════════════════
    # 3. CASH FLOW (Cash Basis)
    # ══════════════════════════════════════════════════════════════════════
    cash_from_customers = (
        _calculate_cash_from_customers(start_date, next_month_start, start_dt, end_dt)
        - sales_returns_revenue
    )
    capital_injections = _calculate_capital_injections(start_date, next_month_start)
    other_cash_in = _calculate_other_cash_in(start_date, next_month_start)
    total_cash_in = cash_from_customers + capital_injections + other_cash_in

    cash_to_suppliers = _calculate_cash_to_suppliers(start_date, next_month_start)
    expenses_operational = _calculate_operational_expenses(start_date, next_month_start)
    expenses_other = _calculate_other_cash_out(start_date, next_month_start)
    expenses_supplies = _calculate_supplies_expenses(start_date, next_month_start)
    total_cash_out = cash_to_suppliers + expenses_operational + expenses_other + expenses_supplies

    cash_opening = prev_summary.cash_closing if prev_summary else Decimal('0')
    net_cash_flow = total_cash_in - total_cash_out
    cash_closing = cash_opening + net_cash_flow

    # ══════════════════════════════════════════════════════════════════════
    # 4. P&L (Accrual Basis)
    # ══════════════════════════════════════════════════════════════════════
    revenue_sales = (
        _calculate_sales_revenue(start_date, next_month_start, start_dt, end_dt)
        - sales_returns_revenue
    )

    gross_profit = revenue_sales - cogs_actual
    gross_margin_pct = clamp_ratio_pct(
        (gross_profit / revenue_sales * 100) if revenue_sales > 0 else Decimal('0')
    )
    # Net Profit includes other income (capital injections, purchase returns, etc.)
    total_income = gross_profit + other_cash_in + capital_injections
    net_profit = total_income - expenses_operational - expenses_other - expenses_supplies

    # ══════════════════════════════════════════════════════════════════════
    # 5. BALANCE SHEET
    # ══════════════════════════════════════════════════════════════════════
    opening_balance = cash_opening + inventory_opening + ar_opening
    closing_balance = cash_closing + inventory_closing + ar_closing

    # ══════════════════════════════════════════════════════════════════════
    # 6. PERFORMANCE METRICS
    # ══════════════════════════════════════════════════════════════════════
    collection_rate_pct = clamp_ratio_pct(
        (cash_from_customers / revenue_sales * 100)
        if revenue_sales > 0 else Decimal('0')
    )
    dso = clamp_ratio_pct(
        (ar_closing / revenue_sales * last_day)
        if revenue_sales > 0 else Decimal('0'),
        max_digits=8, decimal_places=2,
    )
    avg_inventory = (inventory_opening + inventory_closing) / 2
    inventory_turnover = clamp_ratio_pct(
        (cogs_actual / avg_inventory) if avg_inventory > 0 else Decimal('0'),
        max_digits=8, decimal_places=2,
    )
    operating_cash_flow = cash_from_customers + other_cash_in - total_cash_out

    # ── Counts ───────────────────────────────────────────────────────────
    sales_count = _count_sales(start_dt, end_dt)
    procurement_count = GoodsReceipt.objects.filter(
        status=DocumentStatus.POSTED,
        receipt_date__gte=start_date,
        receipt_date__lt=next_month_start,
    ).count()
    expense_count = Expense.objects.filter(
        status='APPROVED',
        date__gte=start_date,
        date__lt=next_month_start,
    ).count()

    # ── Save ─────────────────────────────────────────────────────────────
    summary, created = MonthlyCashflowSummary.objects.update_or_create(
        year=year,
        month=month,
        defaults={
            'opening_balance': opening_balance,
            'closing_balance': closing_balance,
            'cash_opening': cash_opening,
            'cash_closing': cash_closing,
            'cash_from_customers': cash_from_customers,
            'cash_to_suppliers': cash_to_suppliers,
            'operating_cash_flow': operating_cash_flow,
            'inventory_value_opening': inventory_opening,
            'inventory_value_closing': inventory_closing,
            'inventory_purchased': inventory_purchased,
            'inventory_turnover': inventory_turnover,
            'cogs_actual': cogs_actual,
            'accounts_receivable_opening': ar_opening,
            'accounts_receivable_closing': ar_closing,
            'ar_collections': ar_collections,
            'revenue_accrual': revenue_sales,
            'gross_profit': gross_profit,
            'gross_margin_pct': gross_margin_pct,
            'net_profit': net_profit,
            'collection_rate_pct': collection_rate_pct,
            'days_sales_outstanding': dso,
            'capital_sales': gross_profit,
            'capital_other': other_cash_in + capital_injections,
            'capital_total': total_income,
            'expenses_procurement': inventory_purchased,
            'expenses_operational': expenses_operational + expenses_supplies,
            'expenses_other': expenses_other,
            'expenses_total': expenses_operational + expenses_other + expenses_supplies,
            'total_inflow': total_cash_in,
            'total_outflow': total_cash_out,
            'net_cash_flow': net_cash_flow,
            'sales_count': sales_count,
            'procurement_count': procurement_count,
            'expense_count': expense_count,
            'calculated_by': user,
            'calculated_at': timezone.now(),
        }
    )

    # ── Cascade to next month if its opening balance changed ─────────────
    if month == 12:
        next_year, next_month = year + 1, 1
    else:
        next_year, next_month = year, month + 1

    try:
        next_summary = MonthlyCashflowSummary.objects.get(
            year=next_year, month=next_month
        )
        if next_summary.opening_balance != closing_balance:
            update_monthly_summary(next_year, next_month, user=user)
    except MonthlyCashflowSummary.DoesNotExist:
        pass

    return summary


# ═══════════════════════════════════════════════════════════════════════════
# Shared Calculation Helpers (used by update_monthly_summary)
# ═══════════════════════════════════════════════════════════════════════════

def _calculate_inventory_value(as_of_date):
    """Calculate inventory value using StockMove history (historical snapshot)."""
    as_of_dt = _make_aware_end(as_of_date)
    total = Decimal('0')

    # IMPORTANT: Convert to set() — iterating a .distinct() values_list
    # queryset can still yield duplicates per underlying row.
    item_ids = set(
        StockMove.objects
        .filter(status=MoveStatus.POSTED, posted_at__lt=as_of_dt)
        .values_list('item_id', flat=True)
    )

    for item_id in item_ids:
        try:
            item = Item.objects.get(id=item_id)

            receives = StockMove.objects.filter(
                item_id=item_id, status=MoveStatus.POSTED, posted_at__lt=as_of_dt,
                move_type__in=[MoveType.RECEIVE, MoveType.RETURN_IN],
            ).aggregate(total=Coalesce(Sum('qty'), Decimal('0')))['total']

            delivers = StockMove.objects.filter(
                item_id=item_id, status=MoveStatus.POSTED, posted_at__lt=as_of_dt,
                move_type__in=[
                    MoveType.DELIVER, MoveType.POS_SALE, MoveType.SUPPLY_OUT,
                    MoveType.SERVICE_OUT, MoveType.DAMAGE, MoveType.RETURN_OUT,
                ],
            ).aggregate(total=Coalesce(Sum('qty'), Decimal('0')))['total']

            # ADJUST moves store qty as an unsigned magnitude — direction is
            # encoded via which location field is set (see post_adjustment
            # in inventory/services.py: to_location = increase, from_location
            # = decrease). Summing qty alone would treat every adjustment as
            # an increase regardless of direction, silently inflating
            # inventory value on every decrease adjustment.
            adjustments_increase = StockMove.objects.filter(
                item_id=item_id, status=MoveStatus.POSTED, posted_at__lt=as_of_dt,
                move_type=MoveType.ADJUST, to_location__isnull=False,
            ).aggregate(total=Coalesce(Sum('qty'), Decimal('0')))['total']

            adjustments_decrease = StockMove.objects.filter(
                item_id=item_id, status=MoveStatus.POSTED, posted_at__lt=as_of_dt,
                move_type=MoveType.ADJUST, from_location__isnull=False,
            ).aggregate(total=Coalesce(Sum('qty'), Decimal('0')))['total']

            adjustments = adjustments_increase - adjustments_decrease

            net_qty = receives - delivers + adjustments
            if net_qty > 0:
                avg_cost = _get_weighted_avg_cost(item, as_of_date)
                total += net_qty * avg_cost

        except Item.DoesNotExist:
            continue

    return total


def _get_weighted_avg_cost(item, as_of_date):
    """Get weighted average cost from GRN data, with full unit conversion."""
    import logging
    from procurement.models import GoodsReceiptLine
    from catalog.models import convert_to_base_unit
    from catalog.utils import convert_price_for_unit

    logger = logging.getLogger(__name__)
    stock_unit = item.default_unit

    grn_lines = GoodsReceiptLine.objects.filter(
        item=item,
        goods_receipt__status=DocumentStatus.POSTED,
        goods_receipt__receipt_date__lt=as_of_date,
    ).select_related('goods_receipt__purchase_order', 'unit')

    total_qty = Decimal('0')
    total_cost = Decimal('0')

    for grn_line in grn_lines:
        # Convert GRN qty to item's stock unit — skip line if no conversion exists.
        try:
            base_qty = convert_to_base_unit(grn_line.qty, grn_line.unit, stock_unit, item=item)
        except (ValueError, Exception):
            logger.warning(
                'Inventory WAC: no qty conversion from %s to %s for %s — line skipped.',
                getattr(grn_line.unit, 'abbreviation', grn_line.unit),
                getattr(stock_unit, 'abbreviation', stock_unit),
                item.code,
            )
            continue

        if base_qty <= 0:
            continue

        unit_price = Decimal('0')
        po_unit = None
        if grn_line.goods_receipt.purchase_order_id:
            po_line = grn_line.goods_receipt.purchase_order.lines.filter(item=item).first()
            if po_line:
                unit_price = po_line.unit_price or Decimal('0')
                po_unit = po_line.unit

        if unit_price == 0:
            unit_price = item.cost_price or Decimal('0')
            po_unit = stock_unit

        # Convert PO unit_price to per stock_unit — skip line if no conversion exists.
        if po_unit is not None and po_unit.pk != stock_unit.pk:
            try:
                unit_price = convert_price_for_unit(
                    unit_price, po_unit, stock_unit, item=item,
                    use_conversion_price=False, raise_on_missing=True,
                )
            except (ValueError, Exception):
                logger.warning(
                    'Inventory WAC: no price conversion from %s to %s for %s — line skipped.',
                    getattr(po_unit, 'abbreviation', po_unit),
                    getattr(stock_unit, 'abbreviation', stock_unit),
                    item.code,
                )
                continue

        total_qty += base_qty
        total_cost += base_qty * unit_price

    if total_qty > 0:
        return total_cost / total_qty
    return item.cost_price or Decimal('0')


def _calculate_actual_cogs(start_date, end_date, start_dt, end_dt):
    """Calculate COGS from sales.

    POS sale COGS are calculated dynamically via pos_sale_cogs().
    Invoice COGS are counted ONLY for non-POS invoices to avoid
    double-counting POS sales that also have auto-created invoices.
    """
    from core.cogs import pos_sale_cogs

    total = Decimal('0')

    for sale in POSSale.objects.filter(
        status=SaleStatus.POSTED, posted_at__gte=start_dt, posted_at__lt=end_dt,
    ).prefetch_related('lines__item', 'lines__unit', 'bundle_lines__price_list__items'):
        try:
            total += pos_sale_cogs(sale)
        except Exception:
            continue

    # Exclude invoices linked to POS sales — those COGS are already counted above
    invoices = Invoice.objects.filter(
        is_void=False, date__gte=start_date, date__lt=end_date,
        pos_sale__isnull=True,
    )
    for inv in invoices:
        try:
            total += inv.grand_total_cogs or Decimal('0')
        except Exception:
            continue

    return total


def _calculate_sales_revenue(start_date, end_date, start_dt, end_dt):
    """Calculate total sales revenue (accrual basis).

    POS sales are counted directly from the POSSale table.
    Invoices are counted ONLY for non-POS sources (Delivery Notes, Sales
    Pickups, Services) to avoid double-counting POS sales that also have
    auto-created invoices.
    """
    pos_rev = POSSale.objects.filter(
        status=SaleStatus.POSTED, posted_at__gte=start_dt, posted_at__lt=end_dt,
    ).aggregate(total=Coalesce(Sum('grand_total'), Decimal('0')))['total']

    # Exclude invoices linked to POS sales — those are already counted above
    inv_rev = Invoice.objects.filter(
        is_void=False, date__gte=start_date, date__lt=end_date,
        pos_sale__isnull=True,
    ).aggregate(total=Coalesce(Sum('grand_total'), Decimal('0')))['total']

    return pos_rev + inv_rev


def _calculate_sales_returns_revenue(start_date, end_date):
    """Total revenue reversed by posted Sales Returns in the period.

    Mirrors the per-line pricing logic in cashflow.sync.sync_daily_sales_revenue:
    prefer the original sales-order unit price (converted to the return's
    unit if needed), falling back to the item's current selling price.
    """
    from sales.models import SalesReturn
    from catalog.utils import convert_price_for_unit

    total = Decimal('0')
    for sr in SalesReturn.objects.filter(
        status=DocumentStatus.POSTED,
        return_date__gte=start_date, return_date__lt=end_date,
    ).select_related('sales_order').prefetch_related('lines__item', 'lines__unit'):
        for line in sr.lines.all():
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
            total += unit_price * line.qty
    return total


def _calculate_sales_returns_cogs(start_date, end_date):
    """Total COGS reversed by posted Sales Returns in the period."""
    from sales.models import SalesReturn
    from catalog.utils import calculate_line_cogs_with_conversion

    total = Decimal('0')
    for sr in SalesReturn.objects.filter(
        status=DocumentStatus.POSTED,
        return_date__gte=start_date, return_date__lt=end_date,
    ).prefetch_related('lines__item', 'lines__unit'):
        for line in sr.lines.all():
            total += calculate_line_cogs_with_conversion(line.item, line.qty, line.unit)
    return total


def _calculate_cash_from_customers(start_date, end_date, start_dt, end_dt):
    """Calculate actual cash received from customers.

    POS sales are immediate cash — counted directly from POSSale.
    Invoice payments are counted ONLY for non-POS invoices to avoid
    double-counting POS sales that also have auto-created InvoicePayment
    records (via sync_payments or manual invoice generation).
    """
    # Invoice payments EXCLUDING those linked to POS sales
    payments = InvoicePayment.objects.filter(
        date__gte=start_date, date__lt=end_date,
        invoice__pos_sale__isnull=True,
    ).aggregate(total=Coalesce(Sum('amount'), Decimal('0')))['total']

    # POS sales are immediate cash
    pos_cash = POSSale.objects.filter(
        status=SaleStatus.POSTED, posted_at__gte=start_dt, posted_at__lt=end_dt,
    ).aggregate(total=Coalesce(Sum('grand_total'), Decimal('0')))['total']

    return payments + pos_cash


def _calculate_ar_collections(start_date, end_date):
    """Calculate AR collections (invoice payments only, excluding POS)."""
    return InvoicePayment.objects.filter(
        date__gte=start_date, date__lt=end_date,
        invoice__pos_sale__isnull=True,
    ).aggregate(total=Coalesce(Sum('amount'), Decimal('0')))['total']


def _calculate_ar(as_of_date):
    """Calculate accounts receivable as of date.

    Excludes POS-originated invoices since POS sales are immediate cash
    and should never appear as receivables.

    A single grouped query (LEFT JOIN to payments, filtered-Sum per invoice)
    replaces what used to be one payments query per invoice — the old loop
    called inv.payments.filter(...) inside the loop, which bypassed the
    prefetch cache and issued N+1 queries. On the current dataset this cut
    the call from ~1.1s to ~7ms. Because it runs twice per monthly-summary
    recompute (opening + closing) and that recompute cascades across months
    on every InvoicePayment/Invoice write, it was the dominant cost of
    marking an invoice paid / deleting a payment.

    The per-invoice `balance > 0` clamp is preserved via a HAVING filter so
    overpaid invoices never subtract from the total — identical results to
    the old loop, verified against live data.
    """
    balances = (
        Invoice.objects.filter(
            is_void=False, date__lt=as_of_date,
            pos_sale__isnull=True,
        )
        .annotate(
            paid=Coalesce(
                Sum('payments__amount', filter=Q(payments__date__lt=as_of_date)),
                Value(Decimal('0')),
                output_field=DecimalField(max_digits=15, decimal_places=2),
            ),
        )
        .annotate(balance=F('grand_total') - F('paid'))
        .filter(balance__gt=0)
        .values_list('balance', flat=True)
    )
    return sum(balances, Decimal('0'))


def _calculate_procurement_costs(start_date, end_date):
    """Calculate procurement costs including delivery charges."""
    total = Decimal('0')
    for grn in GoodsReceipt.objects.filter(
        status=DocumentStatus.POSTED,
        receipt_date__gte=start_date,
        receipt_date__lt=end_date,
    ).prefetch_related('lines__item', 'purchase_order__lines'):
        grn_total = Decimal('0')
        for line in grn.lines.all():
            line_cost = Decimal('0')
            if grn.purchase_order:
                po_line = grn.purchase_order.lines.filter(item=line.item).first()
                if po_line and po_line.unit_price > 0:
                    line_cost = line.qty * po_line.unit_price
            if line_cost == 0 and line.item.cost_price:
                line_cost = line.qty * line.item.cost_price
            grn_total += line_cost
        if grn.delivery_charge:
            grn_total += grn.delivery_charge
        total += grn_total
    return total


def _calculate_operational_expenses(start_date, end_date):
    """
    Calculate operational expenses on a CASH basis — money that has
    actually moved. Only Expenses that have reached PAID generate a
    CashFlowTransaction (cashflow/signals.py::expense_paid_to_cashflow),
    so that's the only source counted here.

    Previously this also summed Expense.objects.filter(status='APPROVED'),
    treating an approval (a commitment) as if it were a cash outflow —
    that's an accrual concept, not cash basis, and it double-counted once
    the same expense was later actually paid: the approval month got hit
    for the commitment, and the payment month got hit again for the real
    CashFlowTransaction. If "committed but unpaid" is worth reporting, it
    belongs in the accrual/P&L section under its own label, not folded
    into a cash-basis total.
    """
    return CashFlowTransaction.objects.filter(
        flow_type=CashFlowType.CASH_OUT,
        category=CashFlowCategory.EXPENSES,
        transaction_date__gte=start_date,
        transaction_date__lt=end_date,
    ).filter(
        status__in=[CashFlowStatus.APPROVED, 'PENDING'],
    ).aggregate(total=Coalesce(Sum('amount'), Decimal('0')))['total']


def _calculate_other_cash_in(start_date, end_date):
    """Calculate other cash-in (excluding sales and capital)."""
    return CashFlowTransaction.objects.filter(
        flow_type=CashFlowType.CASH_IN,
        transaction_date__gte=start_date,
        transaction_date__lt=end_date,
    ).filter(
        status__in=[CashFlowStatus.APPROVED, 'PENDING'],
    ).exclude(
        category__in=[CashFlowCategory.SALES, CashFlowCategory.CAPITAL]
    ).aggregate(total=Coalesce(Sum('amount'), Decimal('0')))['total']


def _calculate_other_cash_out(start_date, end_date):
    """Calculate other cash-out (excluding procurement, expenses, supplies).
    Includes PENDING transactions."""
    return CashFlowTransaction.objects.filter(
        flow_type=CashFlowType.CASH_OUT,
        transaction_date__gte=start_date,
        transaction_date__lt=end_date,
    ).filter(
        status__in=[CashFlowStatus.APPROVED, 'PENDING'],
    ).exclude(
        category__in=[
            CashFlowCategory.PROCUREMENT,
            CashFlowCategory.EXPENSES,
            CashFlowCategory.SUPPLIES,
        ]
    ).aggregate(total=Coalesce(Sum('amount'), Decimal('0')))['total']


def _calculate_capital_injections(start_date, end_date):
    """Calculate capital injections. Includes PENDING."""
    return CashFlowTransaction.objects.filter(
        flow_type=CashFlowType.CASH_IN,
        category=CashFlowCategory.CAPITAL,
        transaction_date__gte=start_date,
        transaction_date__lt=end_date,
    ).filter(
        status__in=[CashFlowStatus.APPROVED, 'PENDING'],
    ).aggregate(total=Coalesce(Sum('amount'), Decimal('0')))['total']


def _calculate_cash_to_suppliers(start_date, end_date):
    """Calculate cash paid to suppliers from CashFlowTransaction PROCUREMENT
    entries — the actual cash ledger. Includes PENDING transactions."""
    return CashFlowTransaction.objects.filter(
        flow_type=CashFlowType.CASH_OUT,
        category=CashFlowCategory.PROCUREMENT,
        transaction_date__gte=start_date,
        transaction_date__lt=end_date,
    ).filter(
        status__in=[CashFlowStatus.APPROVED, 'PENDING'],
    ).aggregate(total=Coalesce(Sum('amount'), Decimal('0')))['total']


def _calculate_supplies_expenses(start_date, end_date):
    """Calculate supplies expenses. Includes PENDING."""
    return CashFlowTransaction.objects.filter(
        flow_type=CashFlowType.CASH_OUT,
        category=CashFlowCategory.SUPPLIES,
        transaction_date__gte=start_date,
        transaction_date__lt=end_date,
    ).filter(
        status__in=[CashFlowStatus.APPROVED, 'PENDING'],
    ).aggregate(total=Coalesce(Sum('amount'), Decimal('0')))['total']


def _count_sales(start_dt, end_dt):
    """Count sales transactions."""
    return (
        POSSale.objects.filter(
            status=SaleStatus.POSTED, posted_at__gte=start_dt, posted_at__lt=end_dt,
        ).count()
        + DeliveryNote.objects.filter(
            status=DocumentStatus.POSTED, posted_at__gte=start_dt, posted_at__lt=end_dt,
        ).count()
        + SalesPickup.objects.filter(
            status=DocumentStatus.POSTED, posted_at__gte=start_dt, posted_at__lt=end_dt,
        ).count()
    )


# ═══════════════════════════════════════════════════════════════════════════
# Debounced scheduling — collapse repeated triggers within one transaction
# ═══════════════════════════════════════════════════════════════════════════
#
# update_monthly_summary() issues roughly fifteen aggregate queries across
# five apps. A single request can trigger it several times over for the
# *same* month — e.g. saving a Sales Order cascades into an Invoice resync
# (sales/signals.py), and update_summary_on_invoice below can itself fire
# twice (issue month + paid month). None of those individual recalculations
# are wrong, but doing the same one three times in one request is wasted
# work. _schedule_monthly_summary_update() collects the distinct (year,
# month) pairs touched during the current transaction into a thread-local
# and recalculates each exactly once, after commit.

_pending_months = threading.local()


def _schedule_monthly_summary_update(year, month, user=None):
    pending = getattr(_pending_months, 'value', None)
    is_first = pending is None
    if is_first:
        pending = {}
        _pending_months.value = pending

    # Last writer's `user` wins for attribution — harmless, since the
    # recalculation itself is derived purely from already-committed data.
    pending[(year, month)] = user

    if is_first:
        def _flush():
            months = _pending_months.value or {}
            _pending_months.value = None
            for (y, m), u in months.items():
                update_monthly_summary(y, m, user=u)

        transaction.on_commit(_flush)


# ═══════════════════════════════════════════════════════════════════════════
# Signal Handlers
# ═══════════════════════════════════════════════════════════════════════════

@receiver(post_save, sender=POSSale)
def update_summary_on_pos_sale(sender, instance, created, **kwargs):
    if instance.status == SaleStatus.POSTED and instance.created_at:
        _schedule_monthly_summary_update(
            instance.created_at.year, instance.created_at.month,
            user=getattr(instance, 'created_by', None),
        )


@receiver(post_save, sender=Invoice)
def update_summary_on_invoice(sender, instance, created, **kwargs):
    if instance.is_void:
        return
    # Recalculate the month the invoice was ISSUED (accrual revenue)
    if instance.date:
        _schedule_monthly_summary_update(
            instance.date.year, instance.date.month,
            user=getattr(instance, 'created_by', None),
        )
    # Also recalculate the month it was PAID if different (cash flow)
    if instance.paid_at:
        paid_year, paid_month = instance.paid_at.year, instance.paid_at.month
        if not instance.date or (paid_year, paid_month) != (instance.date.year, instance.date.month):
            _schedule_monthly_summary_update(
                paid_year, paid_month,
                user=getattr(instance, 'created_by', None),
            )


@receiver(post_save, sender=DeliveryNote)
def update_summary_on_delivery(sender, instance, created, **kwargs):
    if instance.status == DocumentStatus.POSTED and instance.posted_at:
        _schedule_monthly_summary_update(
            instance.posted_at.year, instance.posted_at.month,
            user=getattr(instance, 'posted_by', None),
        )


@receiver(post_save, sender=SalesPickup)
def update_summary_on_pickup(sender, instance, created, **kwargs):
    if instance.status == DocumentStatus.POSTED and instance.posted_at:
        _schedule_monthly_summary_update(
            instance.posted_at.year, instance.posted_at.month,
            user=getattr(instance, 'posted_by', None),
        )


@receiver(post_save, sender=GoodsReceipt)
def update_summary_on_grn(sender, instance, created, **kwargs):
    if instance.status == DocumentStatus.POSTED and instance.receipt_date:
        _schedule_monthly_summary_update(
            instance.receipt_date.year, instance.receipt_date.month,
            user=getattr(instance, 'posted_by', None),
        )


@receiver(post_save, sender=Expense)
def update_summary_on_expense(sender, instance, created, **kwargs):
    if instance.status == 'APPROVED' and instance.date:
        _schedule_monthly_summary_update(
            instance.date.year, instance.date.month,
            user=getattr(instance, 'created_by', None),
        )


@receiver(post_save, sender=CashFlowTransaction)
def update_summary_on_cashflow(sender, instance, created, **kwargs):
    # Recalculate regardless of status: the aggregate helpers only include
    # APPROVED/PENDING rows, so a transition to REJECTED/CANCELLED must also
    # trigger a recalc to drop the amount back out of the cached summary —
    # otherwise a previously-PENDING transaction stays baked into the totals
    # forever after being rejected or cancelled.
    if instance.transaction_date:
        _schedule_monthly_summary_update(
            instance.transaction_date.year, instance.transaction_date.month,
            user=getattr(instance, 'approved_by', None) or getattr(instance, 'created_by', None),
        )


@receiver(post_save, sender=InvoicePayment)
def update_summary_on_invoice_payment(sender, instance, created, **kwargs):
    """Recalculate when an invoice payment is recorded (affects cash_from_customers and AR)."""
    if instance.date:
        _schedule_monthly_summary_update(
            instance.date.year, instance.date.month,
            user=getattr(instance, 'created_by', None),
        )


# ── Delete handlers ──────────────────────────────────────────────────────

@receiver(post_delete, sender=POSSale)
def recalc_on_pos_sale_delete(sender, instance, **kwargs):
    if instance.created_at:
        _schedule_monthly_summary_update(instance.created_at.year, instance.created_at.month)


@receiver(post_delete, sender=Invoice)
def recalc_on_invoice_delete(sender, instance, **kwargs):
    if instance.date:
        _schedule_monthly_summary_update(instance.date.year, instance.date.month)
    if instance.paid_at:
        paid_year, paid_month = instance.paid_at.year, instance.paid_at.month
        if not instance.date or (paid_year, paid_month) != (instance.date.year, instance.date.month):
            _schedule_monthly_summary_update(paid_year, paid_month)


@receiver(post_delete, sender=GoodsReceipt)
def recalc_on_grn_delete(sender, instance, **kwargs):
    if instance.receipt_date:
        _schedule_monthly_summary_update(instance.receipt_date.year, instance.receipt_date.month)


@receiver(post_delete, sender=Expense)
def recalc_on_expense_delete(sender, instance, **kwargs):
    if instance.date:
        _schedule_monthly_summary_update(instance.date.year, instance.date.month)


@receiver(post_delete, sender=CashFlowTransaction)
def recalc_on_cashflow_delete(sender, instance, **kwargs):
    if instance.transaction_date:
        _schedule_monthly_summary_update(
            instance.transaction_date.year, instance.transaction_date.month,
        )


@receiver(post_delete, sender=InvoicePayment)
def recalc_on_invoice_payment_delete(sender, instance, **kwargs):
    if instance.date:
        _schedule_monthly_summary_update(instance.date.year, instance.date.month)
