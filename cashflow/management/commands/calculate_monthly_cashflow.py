"""
Management command: calculate_monthly_cashflow
===============================================
Calculates or recalculates monthly cashflow summaries from all posted
transactions, sales, procurements, and expenses.

Usage:
    python manage.py calculate_monthly_cashflow                    # all months
    python manage.py calculate_monthly_cashflow --year 2024        # specific year
    python manage.py calculate_monthly_cashflow --year 2024 --month 3  # specific month
    python manage.py calculate_monthly_cashflow --dry-run          # preview only
"""
from collections import defaultdict
from decimal import Decimal
from datetime import date

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Sum, Q
from django.utils import timezone

from cashflow.models import (
    MonthlyCashflowSummary,
    CashFlowTransaction,
    CashFlowType,
    CashFlowStatus,
    CashFlowCategory,
)
from core.models import Expense, DocumentStatus
from pos.models import POSSale, SaleStatus
from sales.models import DeliveryNote, SalesPickup
from procurement.models import GoodsReceipt


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
            # All months with any transaction data
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
        from django.db.models.functions import ExtractYear, ExtractMonth

        periods = set()

        # From CashFlowTransaction
        for dt in CashFlowTransaction.objects.filter(
            status=CashFlowStatus.APPROVED
        ).values_list('transaction_date', flat=True).distinct():
            if dt:
                periods.add((dt.year, dt.month))

        # From POSSale
        for dt in POSSale.objects.filter(
            status=SaleStatus.POSTED
        ).values_list('created_at', flat=True).distinct():
            if dt:
                periods.add((dt.year, dt.month))

        # From DeliveryNote
        for dt in DeliveryNote.objects.filter(
            status=DocumentStatus.POSTED
        ).values_list('posted_at', flat=True).distinct():
            if dt:
                periods.add((dt.year, dt.month))

        # From SalesPickup
        for dt in SalesPickup.objects.filter(
            status=DocumentStatus.POSTED
        ).values_list('posted_at', flat=True).distinct():
            if dt:
                periods.add((dt.year, dt.month))

        # From GoodsReceipt
        for dt in GoodsReceipt.objects.filter(
            status=DocumentStatus.POSTED
        ).values_list('receipt_date', flat=True).distinct():
            if dt:
                periods.add((dt.year, dt.month))

        # From Expense
        for dt in Expense.objects.filter(
            status='APPROVED'
        ).values_list('date', flat=True).distinct():
            if dt:
                periods.add((dt.year, dt.month))

        return sorted(periods)

    def _calculate_month(self, year, month, dry_run):
        """Calculate cashflow summary for a specific month using accrual accounting."""
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

        # ── Calculate Inventory Values ───────────────────────────────────────
        inventory_opening = self._calculate_inventory_value(start_date)
        inventory_purchased = self._calculate_procurement_costs(start_date, next_month_start)
        
        # ── Calculate COGS (actual expense) ──────────────────────────────────
        cogs_actual = self._calculate_actual_cogs(start_date, next_month_start)
        
        # Calculate closing inventory using formula (not snapshot)
        # Closing = Opening + Purchased - COGS
        inventory_closing = inventory_opening + inventory_purchased - cogs_actual

        # ── Calculate Accounts Receivable ────────────────────────────────────
        ar_opening = self._calculate_ar(start_date)
        ar_closing = self._calculate_ar(next_month_start)
        ar_collections = self._calculate_ar_collections(start_date, next_month_start)
        
        # ── Calculate Cash Position ──────────────────────────────────────────
        # Get previous month's closing cash
        if month == 1:
            prev_summary = MonthlyCashflowSummary.objects.filter(
                year=year - 1, month=12
            ).first()
        else:
            prev_summary = MonthlyCashflowSummary.objects.filter(
                year=year, month=month - 1
            ).first()
        
        # Extract cash from previous total balance
        if prev_summary:
            cash_opening = prev_summary.cash_closing or (
                prev_summary.closing_balance 
                - (prev_summary.inventory_value_closing or Decimal('0'))
                - (prev_summary.accounts_receivable_closing or Decimal('0'))
            )
        else:
            cash_opening = Decimal('0')

        # ── Calculate Capital (Cash In) ──────────────────────────────────────
        # Revenue from sales (without COGS deduction here, we track COGS separately)
        capital_sales_revenue = self._calculate_sales_revenue(start_date, next_month_start)
        capital_other = self._calculate_other_cash_in(start_date, next_month_start)
        capital_total = capital_sales_revenue + capital_other

        # ── Calculate Expenses (Cash Out) ────────────────────────────────────
        # For CASH FLOW: Procurement reduces cash (you paid for inventory)
        # For P&L: COGS is the expense (cost of inventory sold)
        expenses_operational = self._calculate_operational_expenses(start_date, next_month_start)
        expenses_other = self._calculate_other_cash_out(start_date, next_month_start)
        
        # Cash expenses = actual cash spent (procurement + operational + other)
        cash_expenses_total = inventory_purchased + expenses_operational + expenses_other
        
        # P&L expenses = COGS + operational + other (for profit calculation)
        expenses_total = cogs_actual + expenses_operational + expenses_other

        # ── Calculate Cash Flow ──────────────────────────────────────────────
        # Actual cash received from customers (payments)
        cash_from_customers = self._calculate_cash_from_customers(start_date, next_month_start)
        
        # Cash closing = cash opening + all cash in - cash paid
        # Include: customer payments + capital injections + other cash in
        cash_closing = cash_opening + cash_from_customers + capital_other - cash_expenses_total
        
        # Net cash flow = change in cash position
        net_cash_flow = cash_closing - cash_opening

        # ── Calculate Opening/Closing Balance (Total Assets) ────────────────
        # Balance Sheet approach: Total Assets = Cash + Inventory + AR
        opening_balance = cash_opening + inventory_opening + ar_opening
        closing_balance = cash_closing + inventory_closing + ar_closing

        # ── Calculate Net Profit (Gross Profit - Operating Expenses) ─────────
        # P&L uses COGS, not procurement
        gross_profit = capital_sales_revenue - cogs_actual
        net_profit = gross_profit - expenses_operational - expenses_other

        # ── Get counts ───────────────────────────────────────────────────────
        sales_count = self._count_sales(start_date, next_month_start)
        procurement_count = self._count_procurements(start_date, next_month_start)
        expense_count = self._count_expenses(start_date, next_month_start)

        # ── Display summary ──────────────────────────────────────────────────
        self._info(f'  === BALANCE SHEET (Total Assets) ===')
        self._info(f'  Opening Balance:               ₱{opening_balance:,.2f}')
        self._info(f'    • Cash:                      ₱{cash_opening:,.2f}')
        self._info(f'    • Inventory:                 ₱{inventory_opening:,.2f}')
        self._info(f'    • Accounts Receivable:       ₱{ar_opening:,.2f}')
        self._info(f'')
        self._info(f'  === CASH FLOW (Actual Cash Movement) ===')
        self._info(f'  Cash from Customers:           ₱{cash_from_customers:,.2f}')
        self._info(f'  Procurement (Cash Paid):       ₱{inventory_purchased:,.2f}')
        self._info(f'  Operational Expenses:          ₱{expenses_operational:,.2f}')
        self._info(f'  Other Cash-Out:                ₱{expenses_other:,.2f}')
        self._info(f'  Net Cash Flow:                 ₱{net_cash_flow:,.2f}')
        self._info(f'')
        self._info(f'  === P&L (Profit & Loss) ===')
        self._info(f'  Revenue (Sales):               ₱{capital_sales_revenue:,.2f}')
        self._info(f'  Revenue (Other):               ₱{capital_other:,.2f}')
        self._info(f'  Total Revenue:                 ₱{capital_total:,.2f}')
        self._info(f'  COGS (Inventory Sold):         ₱{cogs_actual:,.2f}')
        self._info(f'  Gross Profit:                  ₱{gross_profit:,.2f}')
        self._info(f'  Operating Expenses:            ₱{expenses_operational:,.2f}')
        self._info(f'  Other Expenses:                ₱{expenses_other:,.2f}')
        self._info(f'  Net Profit:                    ₱{net_profit:,.2f}')
        self._info(f'')
        self._info(f'  === BALANCE SHEET (Total Assets) ===')
        self._info(f'  Closing Balance:               ₱{closing_balance:,.2f}')
        self._info(f'    • Cash:                      ₱{cash_closing:,.2f}')
        self._info(f'    • Inventory:                 ₱{inventory_closing:,.2f}')
        self._info(f'    • Accounts Receivable:       ₱{ar_closing:,.2f}')
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
                    
                    # Inventory
                    'inventory_value_opening': inventory_opening,
                    'inventory_value_closing': inventory_closing,
                    'inventory_purchased': inventory_purchased,
                    'cogs_actual': cogs_actual,
                    
                    # Accounts Receivable
                    'accounts_receivable_opening': ar_opening,
                    'accounts_receivable_closing': ar_closing,
                    'ar_collections': ar_collections,
                    
                    # Revenue (P&L)
                    'capital_sales': capital_sales_revenue,
                    'capital_other': capital_other,
                    'capital_total': capital_total,
                    
                    # Expenses
                    'expenses_procurement': inventory_purchased,  # Keep for backward compat
                    'expenses_operational': expenses_operational,
                    'expenses_other': expenses_other,
                    'expenses_total': expenses_total,  # P&L expenses (COGS-based)
                    
                    # Cash Flow
                    'total_inflow': capital_total,
                    'total_outflow': cash_expenses_total,
                    'net_cash_flow': net_cash_flow,  # ✅ FIX: Now reflects actual cash movement
                    
                    # Profit & Loss
                    'net_profit': net_profit,
                    'gross_profit': gross_profit,
                    
                    # Counts
                    'sales_count': sales_count,
                    'procurement_count': procurement_count,
                    'expense_count': expense_count,
                    
                    'calculated_at': timezone.now(),
                }
            )
            action = 'Created' if created else 'Updated'
            self._info(f'  {action} summary record.')

    def _calculate_inventory_value(self, as_of_date):
        """Calculate total inventory asset value as of a specific date."""
        from inventory.models import StockBalance
        
        total_value = Decimal('0')
        
        # Get all stock balances with positive quantity
        balances = StockBalance.objects.filter(
            qty_on_hand__gt=0
        ).select_related('item')
        
        for balance in balances:
            item = balance.item
            qty = balance.qty_on_hand
            
            # Use weighted average cost (stored in item.cost_price)
            cost_price = item.cost_price or Decimal('0')
            
            # Calculate value for this item/location
            value = qty * cost_price
            total_value += value
        
        return total_value

    def _calculate_actual_cogs(self, start_date, end_date):
        """Calculate actual COGS from sales and services (inventory consumed)."""
        from core.cogs import pos_sale_cogs
        from core.models import Invoice
        
        total_cogs = Decimal('0')
        
        # POS Sales COGS
        pos_sales = POSSale.objects.filter(
            status=SaleStatus.POSTED,
            posted_at__gte=start_date,
            posted_at__lt=end_date,
        ).prefetch_related('lines__item', 'lines__unit', 'bundle_lines__price_list__items')
        
        for sale in pos_sales:
            try:
                cogs = pos_sale_cogs(sale)
                total_cogs += cogs
            except Exception:
                # Skip sales with errors
                continue
        
        # Invoice COGS (from Delivery Notes, Pickups, Services)
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

    def _calculate_sales_revenue(self, start_date, end_date):
        """Calculate total sales revenue (without COGS deduction)."""
        from core.models import Invoice
        
        total_revenue = Decimal('0')
        
        # POS Sales revenue
        pos_sales = POSSale.objects.filter(
            status=SaleStatus.POSTED,
            posted_at__gte=start_date,
            posted_at__lt=end_date,
        )
        for sale in pos_sales:
            total_revenue += sale.grand_total or Decimal('0')
        
        # Invoice revenue
        invoices = Invoice.objects.filter(
            is_void=False,
            date__gte=start_date,
            date__lt=end_date,
        )
        for inv in invoices:
            total_revenue += inv.grand_total or Decimal('0')
        
        return total_revenue

    def _calculate_sales_gross_profit(self, start_date, end_date):
        """Calculate gross profit from all sales (revenue - COGS)."""
        from core.cogs import pos_sale_cogs
        total = Decimal('0')

        # POS Sales - calculate COGS dynamically
        pos_sales = POSSale.objects.filter(
            status=SaleStatus.POSTED,
            created_at__gte=start_date,
            created_at__lt=end_date,
        ).prefetch_related('lines__item', 'lines__unit', 'bundle_lines__price_list__items')
        
        for sale in pos_sales:
            try:
                revenue = sale.grand_total or Decimal('0')
                cogs = pos_sale_cogs(sale)
                gross_profit = revenue - cogs
                total += gross_profit
            except Exception:
                # Skip sales with missing items, use revenue only
                total += (sale.grand_total or Decimal('0'))
                continue

        # Invoices - use stored grand_total_cogs
        from core.models import Invoice
        invoices = Invoice.objects.filter(
            is_void=False,
            paid_at__gte=start_date,
            paid_at__lt=end_date,
        )
        for inv in invoices:
            try:
                gross_profit = (inv.grand_total or Decimal('0')) - (inv.grand_total_cogs or Decimal('0'))
                total += gross_profit
            except Exception:
                # Skip invoices with errors
                continue

        return total

    def _calculate_other_cash_in(self, start_date, end_date):
        """Calculate other cash-in transactions (capital, investments, etc.)."""
        result = CashFlowTransaction.objects.filter(
            status=CashFlowStatus.APPROVED,
            flow_type=CashFlowType.CASH_IN,
            transaction_date__gte=start_date,
            transaction_date__lt=end_date,
        ).exclude(
            category=CashFlowCategory.SALES  # Exclude sales, already counted above
        ).aggregate(total=Sum('amount'))
        return result['total'] or Decimal('0')

    def _calculate_procurement_costs(self, start_date, end_date):
        """Calculate total procurement costs from posted GRNs."""
        total = Decimal('0')

        grns = GoodsReceipt.objects.filter(
            status=DocumentStatus.POSTED,
            receipt_date__gte=start_date,
            receipt_date__lt=end_date,
        ).prefetch_related('lines')

        for grn in grns:
            for line in grn.lines.all():
                # Cost = qty * unit_price (from PO line if available)
                if grn.purchase_order:
                    po_line = grn.purchase_order.lines.filter(item=line.item).first()
                    if po_line:
                        cost = line.qty * po_line.unit_price
                        total += cost

        return total

    def _calculate_operational_expenses(self, start_date, end_date):
        """Calculate operational expenses (utilities, salaries, etc.) - excludes COGS/procurement."""
        result = Expense.objects.filter(
            status='APPROVED',
            date__gte=start_date,
            date__lt=end_date,
            category__is_cogs=False,  # Exclude procurement/COGS expenses
        ).aggregate(total=Sum('amount'))
        return result['total'] or Decimal('0')

    def _calculate_other_cash_out(self, start_date, end_date):
        """Calculate other cash-out transactions."""
        result = CashFlowTransaction.objects.filter(
            status=CashFlowStatus.APPROVED,
            flow_type=CashFlowType.CASH_OUT,
            transaction_date__gte=start_date,
            transaction_date__lt=end_date,
        ).exclude(
            category__in=[CashFlowCategory.PROCUREMENT, CashFlowCategory.EXPENSES]
        ).aggregate(total=Sum('amount'))
        return result['total'] or Decimal('0')

    def _count_sales(self, start_date, end_date):
        """Count number of sales transactions."""
        pos_count = POSSale.objects.filter(
            status=SaleStatus.POSTED,
            created_at__gte=start_date,
            created_at__lt=end_date,
        ).count()

        dn_count = DeliveryNote.objects.filter(
            status=DocumentStatus.POSTED,
            posted_at__gte=start_date,
            posted_at__lt=end_date,
        ).count()

        pickup_count = SalesPickup.objects.filter(
            status=DocumentStatus.POSTED,
            posted_at__gte=start_date,
            posted_at__lt=end_date,
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

    def _calculate_ar(self, as_of_date):
        """Calculate accounts receivable (unpaid invoices) as of date."""
        from core.models import Invoice
        
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

    def _calculate_cash_from_customers(self, start_date, end_date):
        """Calculate actual cash received from customers."""
        from core.models import InvoicePayment
        
        total = Decimal('0')
        
        # Invoice payments (actual cash received)
        payments = InvoicePayment.objects.filter(
            date__gte=start_date,
            date__lt=end_date,
        )
        total += payments.aggregate(Sum('amount'))['amount__sum'] or Decimal('0')
        
        # POS sales (assume immediate payment)
        pos_sales = POSSale.objects.filter(
            status=SaleStatus.POSTED,
            posted_at__gte=start_date,
            posted_at__lt=end_date,
        )
        total += pos_sales.aggregate(Sum('grand_total'))['grand_total__sum'] or Decimal('0')
        
        return total

    def _calculate_ar_collections(self, start_date, end_date):
        """Calculate actual AR collections (invoice payments only, excluding POS)."""
        from core.models import InvoicePayment
        
        payments = InvoicePayment.objects.filter(
            date__gte=start_date,
            date__lt=end_date,
        )
        return payments.aggregate(Sum('amount'))['amount__sum'] or Decimal('0')

    def _info(self, msg):
        """Print info message unless quiet mode."""
        if not self.quiet:
            self.stdout.write(msg)
