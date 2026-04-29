"""
Management command: calculate_monthly_cashflow
===============================================
Calculates or recalculates monthly cashflow summaries from all posted
transactions, sales, procurements, and expenses.

This command properly separates:
  - CASH FLOW STATEMENT: Actual cash movement (cash basis)
  - PROFIT & LOSS: Revenue recognition and expense matching (accrual basis)
  - BALANCE SHEET: Total assets = Cash + Inventory + AR

Standard Accounting Formulas:
  Cash Flow:
    Cash Inflow  = Cash from Customers + Capital Injections + Other Cash-In
    Cash Outflow = Cash to Suppliers + Operating Expenses + Other Cash-Out
    Net Cash Flow = Cash Inflow - Cash Outflow
    Closing Cash = Opening Cash + Net Cash Flow

  P&L (Accrual):
    Gross Profit = Revenue - COGS
    Net Profit   = Gross Profit - Operating Expenses - Other Expenses

  Balance Sheet:
    Total Assets = Cash + Inventory + AR
    Opening Balance = Previous month's closing balance
    Closing Balance = Closing Cash + Closing Inventory + Closing AR

  Inventory:
    Closing Inventory = Opening Inventory + Purchased - COGS (formula-based)
    OR calculated from StockMove history (snapshot-based, more accurate)

Usage:
    python manage.py calculate_monthly_cashflow                    # all months
    python manage.py calculate_monthly_cashflow --year 2024        # specific year
    python manage.py calculate_monthly_cashflow --year 2024 --month 3  # specific month
    python manage.py calculate_monthly_cashflow --dry-run          # preview only
"""
from collections import defaultdict
from datetime import date, datetime, time
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Sum, Q
from django.db.models.functions import Coalesce
from django.utils import timezone

from cashflow.models import (
    MonthlyCashflowSummary,
    CashFlowTransaction,
    CashFlowType,
    CashFlowStatus,
    CashFlowCategory,
)
from core.models import Expense, DocumentStatus, Invoice, InvoicePayment
from pos.models import POSSale, SaleStatus
from sales.models import DeliveryNote, SalesPickup
from procurement.models import GoodsReceipt
from inventory.models import StockMove, StockBalance, MoveType, MoveStatus
from catalog.models import Item


def _make_aware_start(d):
    """Convert a date to a timezone-aware datetime at start of day."""
    return timezone.make_aware(datetime.combine(d, time.min))


def _make_aware_end(d):
    """Convert a date to a timezone-aware datetime at end of day."""
    return timezone.make_aware(datetime.combine(d, time.max))


class Command(BaseCommand):
    help = 'Calculate monthly cashflow summaries from all transactions'

    def add_arguments(self, parser):
        parser.add_argument(
            '--year',
            type=int,
            help='Calculate for specific year (default: all years)',
        )
        parser.add_argument(
            '--month',
            type=int,
            help='Calculate for specific month (1-12, requires --year)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Preview calculations without saving',
        )
        parser.add_argument(
            '--quiet', '-q',
            action='store_true',
            help='Suppress detailed output',
        )

    def handle(self, *args, **options):
        year = options.get('year')
        month = options.get('month')
        dry_run = options['dry_run']
        self.quiet = options['quiet']

        if month and not year:
            self.stdout.write(self.style.ERROR('--month requires --year'))
            return

        if month and (month < 1 or month > 12):
            self.stdout.write(self.style.ERROR('--month must be between 1 and 12'))
            return

        mode = 'DRY-RUN' if dry_run else 'APPLYING'
        self.stdout.write(self.style.SUCCESS(f'\n=== Calculate Monthly Cashflow [{mode}] ===\n'))

        # Determine which months to calculate
        if year and month:
            periods = [(year, month)]
        elif year:
            periods = [(year, m) for m in range(1, 13)]
        else:
            periods = self._get_all_periods()

        if not periods:
            self.stdout.write(self.style.WARNING('No data found to calculate.'))
            return

        self.stdout.write(f'Calculating {len(periods)} month(s)...\n')

        with transaction.atomic():
            for yr, mn in periods:
                self._calculate_month(yr, mn, dry_run)

            if dry_run:
                transaction.set_rollback(True)
                self.stdout.write(self.style.WARNING('\nDry-run complete. No changes saved.'))
            else:
                self.stdout.write(self.style.SUCCESS('\n=== Calculation Complete ==='))

    def _get_all_periods(self):
        """Get all (year, month) tuples that have any transaction data."""
        periods = set()

        for dt in CashFlowTransaction.objects.filter(
            status=CashFlowStatus.APPROVED
        ).values_list('transaction_date', flat=True).distinct():
            if dt:
                periods.add((dt.year, dt.month))

        for dt in POSSale.objects.filter(
            status=SaleStatus.POSTED
        ).values_list('created_at', flat=True).distinct():
            if dt:
                periods.add((dt.year, dt.month))

        for dt in DeliveryNote.objects.filter(
            status=DocumentStatus.POSTED
        ).values_list('posted_at', flat=True).distinct():
            if dt:
                periods.add((dt.year, dt.month))

        for dt in SalesPickup.objects.filter(
            status=DocumentStatus.POSTED
        ).values_list('posted_at', flat=True).distinct():
            if dt:
                periods.add((dt.year, dt.month))

        for dt in GoodsReceipt.objects.filter(
            status=DocumentStatus.POSTED
        ).values_list('receipt_date', flat=True).distinct():
            if dt:
                periods.add((dt.year, dt.month))

        for dt in Expense.objects.filter(
            status='APPROVED'
        ).values_list('date', flat=True).distinct():
            if dt:
                periods.add((dt.year, dt.month))

        return sorted(periods)

    def _calculate_month(self, year, month, dry_run):
        """Calculate cashflow summary for a specific month."""
        from calendar import month_name, monthrange

        self._info(f'\n--- {month_name[month]} {year} ---')

        # Date range for this month
        start_date = date(year, month, 1)
        last_day = monthrange(year, month)[1]
        end_date = date(year, month, last_day)

        if month == 12:
            next_month_start = date(year + 1, 1, 1)
        else:
            next_month_start = date(year, month + 1, 1)

        # Timezone-aware datetimes for DateTimeField queries
        start_dt = _make_aware_start(start_date)
        end_dt = _make_aware_start(next_month_start)  # exclusive upper bound

        # ── Get Previous Month Summary ───────────────────────────────────────
        if month == 1:
            prev_summary = MonthlyCashflowSummary.objects.filter(
                year=year - 1, month=12
            ).first()
        else:
            prev_summary = MonthlyCashflowSummary.objects.filter(
                year=year, month=month - 1
            ).first()

        # ══════════════════════════════════════════════════════════════════════
        # 1. INVENTORY
        # ══════════════════════════════════════════════════════════════════════
        # Use formula-based approach: Closing = Opening + Purchased - COGS
        # Opening comes from previous month's closing (or StockBalance for
        # the latest month as a sanity anchor).
        #
        # StockBalance (rebuilt by resync_inventory from source documents) is
        # the authoritative current snapshot. StockMove sums are unreliable
        # due to unit conversion gaps across ~15 items.
        inventory_purchased = self._calculate_procurement_costs(start_date, next_month_start)
        cogs_actual = self._calculate_actual_cogs(start_date, next_month_start, start_dt, end_dt)

        if prev_summary:
            inventory_opening = prev_summary.inventory_value_closing
        else:
            inventory_opening = Decimal('0')

        # Formula: Closing = Opening + Purchased - COGS
        inventory_closing = inventory_opening + inventory_purchased - cogs_actual
        # Floor at zero — inventory can't be negative in value
        if inventory_closing < 0:
            inventory_closing = Decimal('0')

        # ══════════════════════════════════════════════════════════════════════
        # 2. ACCOUNTS RECEIVABLE
        # ══════════════════════════════════════════════════════════════════════
        ar_opening = self._calculate_ar(start_date)
        ar_closing = self._calculate_ar(next_month_start)
        ar_collections = self._calculate_ar_collections(start_date, next_month_start)

        # ══════════════════════════════════════════════════════════════════════
        # 3. CASH FLOW STATEMENT (Actual Cash Movement)
        # ══════════════════════════════════════════════════════════════════════
        # Cash from customers = Invoice payments + POS sales (immediate cash)
        cash_from_customers = self._calculate_cash_from_customers(
            start_date, next_month_start, start_dt, end_dt
        )

        # Capital injections (owner contributions, loans)
        capital_injections = self._calculate_capital_injections(start_date, next_month_start)

        # Other cash-in (non-sales, non-capital)
        other_cash_in = self._calculate_other_cash_in(start_date, next_month_start)

        # Total cash inflow
        total_cash_in = cash_from_customers + capital_injections + other_cash_in

        # Cash outflows
        cash_to_suppliers = inventory_purchased  # Assume immediate payment for GRNs
        expenses_operational = self._calculate_operational_expenses(start_date, next_month_start)
        expenses_other = self._calculate_other_cash_out(start_date, next_month_start)

        # Total cash outflow
        total_cash_out = cash_to_suppliers + expenses_operational + expenses_other

        # Opening cash from previous month
        if prev_summary:
            cash_opening = prev_summary.cash_closing
        else:
            cash_opening = Decimal('0')

        # Net cash flow and closing cash
        net_cash_flow = total_cash_in - total_cash_out
        cash_closing = cash_opening + net_cash_flow

        # ══════════════════════════════════════════════════════════════════════
        # 4. P&L STATEMENT (Accrual Basis)
        # ══════════════════════════════════════════════════════════════════════
        # Revenue = all sales invoiced/posted this month
        revenue_sales = self._calculate_sales_revenue(start_date, next_month_start, start_dt, end_dt)
        revenue_other = other_cash_in + capital_injections  # For legacy capital_other field

        # Gross profit = Revenue - COGS
        gross_profit = revenue_sales - cogs_actual
        gross_margin_pct = (gross_profit / revenue_sales * 100) if revenue_sales > 0 else Decimal('0')

        # Net profit = Gross Profit - Operating Expenses - Other Expenses
        net_profit = gross_profit - expenses_operational - expenses_other

        # ══════════════════════════════════════════════════════════════════════
        # 5. BALANCE SHEET (Total Assets = Cash + Inventory + AR)
        # ══════════════════════════════════════════════════════════════════════
        opening_balance = cash_opening + inventory_opening + ar_opening
        closing_balance = cash_closing + inventory_closing + ar_closing

        # ══════════════════════════════════════════════════════════════════════
        # 6. PERFORMANCE METRICS
        # ══════════════════════════════════════════════════════════════════════
        # Collection rate
        collection_rate_pct = (
            (cash_from_customers / revenue_sales * 100)
            if revenue_sales > 0 else Decimal('0')
        )

        # Days Sales Outstanding
        dso = (
            (ar_closing / revenue_sales * last_day)
            if revenue_sales > 0 else Decimal('0')
        )

        # Inventory turnover
        avg_inventory = (inventory_opening + inventory_closing) / 2
        inventory_turnover = (
            (cogs_actual / avg_inventory)
            if avg_inventory > 0 else Decimal('0')
        )

        # Operating cash flow (excluding capital injections)
        operating_cash_flow = cash_from_customers + other_cash_in - total_cash_out

        # ── Get counts ───────────────────────────────────────────────────────
        sales_count = self._count_sales(start_date, next_month_start, start_dt, end_dt)
        procurement_count = self._count_procurements(start_date, next_month_start)
        expense_count = self._count_expenses(start_date, next_month_start)

        # ── Display summary ──────────────────────────────────────────────────
        self._info(f'  ┌─ BALANCE SHEET ──────────────────────────────────────────┐')
        self._info(f'  │ Opening Balance:          {self._fmt(opening_balance):>20} │')
        self._info(f'  │   • Cash:                 {self._fmt(cash_opening):>20} │')
        self._info(f'  │   • Inventory:            {self._fmt(inventory_opening):>20} │')
        self._info(f'  │   • AR:                   {self._fmt(ar_opening):>20} │')
        self._info(f'  ├────────────────────────────────────────────────────────────┤')
        self._info(f'  │ Closing Balance:          {self._fmt(closing_balance):>20} │')
        self._info(f'  │   • Cash:                 {self._fmt(cash_closing):>20} │')
        self._info(f'  │   • Inventory:            {self._fmt(inventory_closing):>20} │')
        self._info(f'  │   • AR:                   {self._fmt(ar_closing):>20} │')
        self._info(f'  └────────────────────────────────────────────────────────────┘')
        self._info(f'')
        self._info(f'  ┌─ CASH FLOW ───────────────────────────────────────────────┐')
        self._info(f'  │ Cash In:                                                   │')
        self._info(f'  │   From Customers:         {self._fmt(cash_from_customers):>20} │')
        self._info(f'  │   Capital Injections:     {self._fmt(capital_injections):>20} │')
        self._info(f'  │   Other Cash In:          {self._fmt(other_cash_in):>20} │')
        self._info(f'  │   Total Cash In:          {self._fmt(total_cash_in):>20} │')
        self._info(f'  │ Cash Out:                                                  │')
        self._info(f'  │   To Suppliers:           {self._fmt(cash_to_suppliers):>20} │')
        self._info(f'  │   Operating Expenses:     {self._fmt(expenses_operational):>20} │')
        self._info(f'  │   Other Cash Out:         {self._fmt(expenses_other):>20} │')
        self._info(f'  │   Total Cash Out:         {self._fmt(total_cash_out):>20} │')
        self._info(f'  │ Net Cash Flow:            {self._fmt(net_cash_flow):>20} │')
        self._info(f'  └────────────────────────────────────────────────────────────┘')
        self._info(f'')
        self._info(f'  ┌─ P&L ─────────────────────────────────────────────────────┐')
        self._info(f'  │ Revenue:                  {self._fmt(revenue_sales):>20} │')
        self._info(f'  │ COGS:                     {self._fmt(cogs_actual):>20} │')
        self._info(f'  │ Gross Profit:             {self._fmt(gross_profit):>20} │')
        self._info(f'  │ Gross Margin:             {gross_margin_pct:>19.1f}% │')
        self._info(f'  │ Operating Expenses:       {self._fmt(expenses_operational):>20} │')
        self._info(f'  │ Other Expenses:           {self._fmt(expenses_other):>20} │')
        self._info(f'  │ Net Profit:               {self._fmt(net_profit):>20} │')
        self._info(f'  └────────────────────────────────────────────────────────────┘')
        self._info(f'')
        self._info(f'  Transactions: {sales_count} sales, {procurement_count} procurements, {expense_count} expenses')

        # ── Save or update summary ───────────────────────────────────────────
        if not dry_run:
            summary, created = MonthlyCashflowSummary.objects.update_or_create(
                year=year,
                month=month,
                defaults={
                    # Balance Sheet (Total Assets)
                    'opening_balance': opening_balance,
                    'closing_balance': closing_balance,

                    # Cash Position
                    'cash_opening': cash_opening,
                    'cash_closing': cash_closing,
                    'cash_from_customers': cash_from_customers,
                    'cash_to_suppliers': cash_to_suppliers,
                    'operating_cash_flow': operating_cash_flow,

                    # Inventory
                    'inventory_value_opening': inventory_opening,
                    'inventory_value_closing': inventory_closing,
                    'inventory_purchased': inventory_purchased,
                    'inventory_turnover': inventory_turnover,
                    'cogs_actual': cogs_actual,

                    # Accounts Receivable
                    'accounts_receivable_opening': ar_opening,
                    'accounts_receivable_closing': ar_closing,
                    'ar_collections': ar_collections,

                    # P&L
                    'revenue_accrual': revenue_sales,
                    'gross_profit': gross_profit,
                    'gross_margin_pct': gross_margin_pct,
                    'net_profit': net_profit,

                    # Performance Metrics
                    'collection_rate_pct': collection_rate_pct,
                    'days_sales_outstanding': dso,

                    # Legacy / Dashboard fields
                    'capital_sales': revenue_sales,
                    'capital_other': revenue_other,
                    'capital_total': revenue_sales + revenue_other,
                    'expenses_procurement': inventory_purchased,
                    'expenses_operational': expenses_operational,
                    'expenses_other': expenses_other,
                    'expenses_total': cogs_actual + expenses_operational + expenses_other,

                    # Cash Flow totals
                    'total_inflow': total_cash_in,
                    'total_outflow': total_cash_out,
                    'net_cash_flow': net_cash_flow,

                    # Counts
                    'sales_count': sales_count,
                    'procurement_count': procurement_count,
                    'expense_count': expense_count,

                    'calculated_at': timezone.now(),
                }
            )
            action = 'Created' if created else 'Updated'
            self._info(f'  {action} summary record.')

    # ══════════════════════════════════════════════════════════════════════
    # CALCULATION HELPERS
    # ══════════════════════════════════════════════════════════════════════

    def _calculate_inventory_value_historical(self, as_of_date):
        """
        Calculate inventory value as of a specific date using StockMove history.

        This is the CORRECT approach — it reconstructs the inventory position
        at any point in time by summing all stock movements up to that date,
        then values each item using weighted average cost from GRN data.

        Previous bug: Used StockBalance (current snapshot) which gave the
        SAME value for every month regardless of the as_of_date parameter.
        """
        as_of_dt = _make_aware_end(as_of_date)
        total = Decimal('0')

        # Get all items that had stock movements before the as_of_date
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

                # Calculate net quantity as of date from stock moves
                receives = StockMove.objects.filter(
                    item_id=item_id,
                    status=MoveStatus.POSTED,
                    posted_at__lt=as_of_dt,
                    move_type__in=[MoveType.RECEIVE, MoveType.RETURN_IN],
                ).aggregate(
                    total=Coalesce(Sum('qty'), Decimal('0'))
                )['total']

                delivers = StockMove.objects.filter(
                    item_id=item_id,
                    status=MoveStatus.POSTED,
                    posted_at__lt=as_of_dt,
                    move_type__in=[
                        MoveType.DELIVER, MoveType.POS_SALE,
                        MoveType.SUPPLY_OUT, MoveType.SERVICE_OUT,
                        MoveType.DAMAGE, MoveType.RETURN_OUT,
                    ],
                ).aggregate(
                    total=Coalesce(Sum('qty'), Decimal('0'))
                )['total']

                adjustments = StockMove.objects.filter(
                    item_id=item_id,
                    status=MoveStatus.POSTED,
                    posted_at__lt=as_of_dt,
                    move_type=MoveType.ADJUST,
                ).aggregate(
                    total=Coalesce(Sum('qty'), Decimal('0'))
                )['total']

                net_qty = receives - delivers + adjustments

                if net_qty > 0:
                    # Calculate weighted average cost from GRN purchase prices
                    avg_cost = self._get_weighted_avg_cost(item, as_of_date)
                    total += net_qty * avg_cost

            except Item.DoesNotExist:
                continue

        return total

    def _get_weighted_avg_cost(self, item, as_of_date):
        """
        Calculate weighted average cost for an item from GRN data up to a date.
        Falls back to item.cost_price if no GRN data available.
        """
        from procurement.models import GoodsReceiptLine

        grn_lines = GoodsReceiptLine.objects.filter(
            item=item,
            goods_receipt__status=DocumentStatus.POSTED,
            goods_receipt__receipt_date__lt=as_of_date,
        ).select_related('goods_receipt__purchase_order')

        total_qty = Decimal('0')
        total_cost = Decimal('0')

        for grn_line in grn_lines:
            unit_price = Decimal('0')
            if grn_line.goods_receipt.purchase_order_id:
                po_line = grn_line.goods_receipt.purchase_order.lines.filter(
                    item=item
                ).first()
                if po_line:
                    unit_price = po_line.unit_price or Decimal('0')

            # Fallback to item cost_price
            if unit_price == 0:
                unit_price = item.cost_price or Decimal('0')

            total_qty += grn_line.qty
            total_cost += grn_line.qty * unit_price

        if total_qty > 0:
            return total_cost / total_qty

        return item.cost_price or Decimal('0')

    def _calculate_actual_cogs(self, start_date, end_date, start_dt, end_dt):
        """
        Calculate actual COGS from sales (inventory consumed).

        Uses posted_at for POS sales (when the sale was finalized) and
        date for invoices (when the invoice was issued — accrual basis).
        """
        from core.cogs import pos_sale_cogs

        total_cogs = Decimal('0')

        # POS Sales COGS — use posted_at (when sale was finalized)
        pos_sales = POSSale.objects.filter(
            status=SaleStatus.POSTED,
            posted_at__gte=start_dt,
            posted_at__lt=end_dt,
        ).prefetch_related('lines__item', 'lines__unit', 'bundle_lines__price_list__items')

        for sale in pos_sales:
            try:
                total_cogs += pos_sale_cogs(sale)
            except Exception:
                continue

        # Invoice COGS — use invoice date (accrual basis)
        invoices = Invoice.objects.filter(
            is_void=False,
            date__gte=start_date,
            date__lt=end_date,
        )
        for inv in invoices:
            try:
                total_cogs += inv.grand_total_cogs or Decimal('0')
            except Exception:
                continue

        return total_cogs

    def _calculate_sales_revenue(self, start_date, end_date, start_dt, end_dt):
        """
        Calculate total sales revenue (accrual basis).

        POS sales: use posted_at (when sale was finalized and cash received)
        Invoices: use date (when invoice was issued — accrual recognition)
        """
        total_revenue = Decimal('0')

        # POS Sales revenue
        pos_revenue = POSSale.objects.filter(
            status=SaleStatus.POSTED,
            posted_at__gte=start_dt,
            posted_at__lt=end_dt,
        ).aggregate(
            total=Coalesce(Sum('grand_total'), Decimal('0'))
        )['total']
        total_revenue += pos_revenue

        # Invoice revenue (accrual — when invoiced, not when paid)
        inv_revenue = Invoice.objects.filter(
            is_void=False,
            date__gte=start_date,
            date__lt=end_date,
        ).aggregate(
            total=Coalesce(Sum('grand_total'), Decimal('0'))
        )['total']
        total_revenue += inv_revenue

        return total_revenue

    def _calculate_cash_from_customers(self, start_date, end_date, start_dt, end_dt):
        """
        Calculate actual cash received from customers.

        This is CASH BASIS — when money actually came in:
        - Invoice payments: actual payment date
        - POS sales: posted_at (immediate cash)
        """
        total = Decimal('0')

        # Invoice payments (actual cash received on payment date)
        payments = InvoicePayment.objects.filter(
            date__gte=start_date,
            date__lt=end_date,
        ).aggregate(
            total=Coalesce(Sum('amount'), Decimal('0'))
        )['total']
        total += payments

        # POS sales (immediate cash at point of sale)
        pos_cash = POSSale.objects.filter(
            status=SaleStatus.POSTED,
            posted_at__gte=start_dt,
            posted_at__lt=end_dt,
        ).aggregate(
            total=Coalesce(Sum('grand_total'), Decimal('0'))
        )['total']
        total += pos_cash

        return total

    def _calculate_ar_collections(self, start_date, end_date):
        """Calculate AR collections (invoice payments only, excluding POS)."""
        return InvoicePayment.objects.filter(
            date__gte=start_date,
            date__lt=end_date,
        ).aggregate(
            total=Coalesce(Sum('amount'), Decimal('0'))
        )['total']

    def _calculate_ar(self, as_of_date):
        """Calculate accounts receivable (unpaid invoices) as of date."""
        total = Decimal('0')
        invoices = Invoice.objects.filter(
            is_void=False,
            date__lt=as_of_date,
        ).prefetch_related('payments')

        for inv in invoices:
            paid = sum(p.amount for p in inv.payments.filter(date__lt=as_of_date))
            balance = inv.grand_total - paid
            if balance > 0:
                total += balance

        return total

    def _calculate_procurement_costs(self, start_date, end_date):
        """
        Calculate total procurement costs from posted GRNs.
        Includes delivery charges (previously missing).
        """
        total = Decimal('0')

        grns = GoodsReceipt.objects.filter(
            status=DocumentStatus.POSTED,
            receipt_date__gte=start_date,
            receipt_date__lt=end_date,
        ).prefetch_related('lines__item', 'purchase_order__lines')

        for grn in grns:
            grn_total = Decimal('0')
            for line in grn.lines.all():
                line_cost = Decimal('0')
                if grn.purchase_order:
                    po_line = grn.purchase_order.lines.filter(item=line.item).first()
                    if po_line and po_line.unit_price > 0:
                        line_cost = line.qty * po_line.unit_price

                # Fallback to item cost_price
                if line_cost == 0 and line.item.cost_price:
                    line_cost = line.qty * line.item.cost_price

                grn_total += line_cost

            # Include delivery charge
            if grn.delivery_charge:
                grn_total += grn.delivery_charge

            total += grn_total

        return total

    def _calculate_operational_expenses(self, start_date, end_date):
        """
        Calculate operational expenses from BOTH Expense model AND
        CashFlowTransaction with EXPENSES category.

        Previous bug: Only checked Expense model, missing expense-type
        CashFlowTransactions.
        """
        # From Expense model (exclude COGS/procurement expenses)
        expense_total = Expense.objects.filter(
            status='APPROVED',
            date__gte=start_date,
            date__lt=end_date,
            category__is_cogs=False,
        ).aggregate(
            total=Coalesce(Sum('amount'), Decimal('0'))
        )['total']

        # From CashFlowTransaction with EXPENSES category
        cf_expense_total = CashFlowTransaction.objects.filter(
            status=CashFlowStatus.APPROVED,
            flow_type=CashFlowType.CASH_OUT,
            category=CashFlowCategory.EXPENSES,
            transaction_date__gte=start_date,
            transaction_date__lt=end_date,
        ).aggregate(
            total=Coalesce(Sum('amount'), Decimal('0'))
        )['total']

        return expense_total + cf_expense_total

    def _calculate_other_cash_in(self, start_date, end_date):
        """Calculate other cash-in (excluding sales and capital)."""
        return CashFlowTransaction.objects.filter(
            status=CashFlowStatus.APPROVED,
            flow_type=CashFlowType.CASH_IN,
            transaction_date__gte=start_date,
            transaction_date__lt=end_date,
        ).exclude(
            category__in=[CashFlowCategory.SALES, CashFlowCategory.CAPITAL]
        ).aggregate(
            total=Coalesce(Sum('amount'), Decimal('0'))
        )['total']

    def _calculate_other_cash_out(self, start_date, end_date):
        """Calculate other cash-out (excluding procurement and expenses)."""
        return CashFlowTransaction.objects.filter(
            status=CashFlowStatus.APPROVED,
            flow_type=CashFlowType.CASH_OUT,
            transaction_date__gte=start_date,
            transaction_date__lt=end_date,
        ).exclude(
            category__in=[
                CashFlowCategory.PROCUREMENT,
                CashFlowCategory.EXPENSES,
                CashFlowCategory.SUPPLIES,
            ]
        ).aggregate(
            total=Coalesce(Sum('amount'), Decimal('0'))
        )['total']

    def _calculate_capital_injections(self, start_date, end_date):
        """Calculate capital injections (owner contributions, loans)."""
        return CashFlowTransaction.objects.filter(
            status=CashFlowStatus.APPROVED,
            flow_type=CashFlowType.CASH_IN,
            category=CashFlowCategory.CAPITAL,
            transaction_date__gte=start_date,
            transaction_date__lt=end_date,
        ).aggregate(
            total=Coalesce(Sum('amount'), Decimal('0'))
        )['total']

    def _count_sales(self, start_date, end_date, start_dt, end_dt):
        """Count number of sales transactions."""
        pos_count = POSSale.objects.filter(
            status=SaleStatus.POSTED,
            posted_at__gte=start_dt,
            posted_at__lt=end_dt,
        ).count()

        dn_count = DeliveryNote.objects.filter(
            status=DocumentStatus.POSTED,
            posted_at__gte=start_dt,
            posted_at__lt=end_dt,
        ).count()

        pickup_count = SalesPickup.objects.filter(
            status=DocumentStatus.POSTED,
            posted_at__gte=start_dt,
            posted_at__lt=end_dt,
        ).count()

        return pos_count + dn_count + pickup_count

    def _count_procurements(self, start_date, end_date):
        """Count number of procurement transactions."""
        return GoodsReceipt.objects.filter(
            status=DocumentStatus.POSTED,
            receipt_date__gte=start_date,
            receipt_date__lt=end_date,
        ).count()

    def _count_expenses(self, start_date, end_date):
        """Count number of expense records."""
        return Expense.objects.filter(
            status='APPROVED',
            date__gte=start_date,
            date__lt=end_date,
        ).count()

    def _fmt(self, amount):
        """Format currency amount."""
        return f'₱{amount:,.2f}'

    def _info(self, msg):
        """Print info message unless quiet mode."""
        if not self.quiet:
            self.stdout.write(msg)
