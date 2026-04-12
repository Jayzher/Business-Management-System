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
        """Calculate cashflow summary for a specific month."""
        from calendar import month_name

        self._info(f'\n--- {month_name[month]} {year} ---')

        # Date range for this month
        if month == 12:
            next_month = date(year + 1, 1, 1)
        else:
            next_month = date(year, month + 1, 1)
        start_date = date(year, month, 1)
        end_date = next_month

        # ── Calculate Capital (Cash In) ──────────────────────────────────────
        capital_sales = self._calculate_sales_gross_profit(start_date, end_date)
        capital_other = self._calculate_other_cash_in(start_date, end_date)
        capital_total = capital_sales + capital_other

        # ── Calculate Expenses (Cash Out) ────────────────────────────────────
        expenses_procurement = self._calculate_procurement_costs(start_date, end_date)
        expenses_operational = self._calculate_operational_expenses(start_date, end_date)
        expenses_other = self._calculate_other_cash_out(start_date, end_date)
        expenses_total = expenses_procurement + expenses_operational + expenses_other

        # ── Calculate Net Profit ─────────────────────────────────────────────
        net_profit = capital_total - expenses_total

        # ── Get counts ───────────────────────────────────────────────────────
        sales_count = self._count_sales(start_date, end_date)
        procurement_count = self._count_procurements(start_date, end_date)
        expense_count = self._count_expenses(start_date, end_date)

        # ── Display summary ──────────────────────────────────────────────────
        self._info(f'  Capital (Sales Gross Profit):  ₱{capital_sales:,.2f}')
        self._info(f'  Capital (Other Cash-In):       ₱{capital_other:,.2f}')
        self._info(f'  Capital Total:                 ₱{capital_total:,.2f}')
        self._info(f'')
        self._info(f'  Expenses (Procurement):        ₱{expenses_procurement:,.2f}')
        self._info(f'  Expenses (Operational):        ₱{expenses_operational:,.2f}')
        self._info(f'  Expenses (Other Cash-Out):     ₱{expenses_other:,.2f}')
        self._info(f'  Expenses Total:                ₱{expenses_total:,.2f}')
        self._info(f'')
        self._info(f'  Net Profit:                    ₱{net_profit:,.2f}')
        self._info(f'')
        self._info(f'  Transactions: {sales_count} sales, {procurement_count} procurements, {expense_count} expenses')

        # ── Save or update summary ───────────────────────────────────────────
        if not dry_run:
            summary, created = MonthlyCashflowSummary.objects.update_or_create(
                year=year,
                month=month,
                defaults={
                    'capital_sales': capital_sales,
                    'capital_other': capital_other,
                    'capital_total': capital_total,
                    'expenses_procurement': expenses_procurement,
                    'expenses_operational': expenses_operational,
                    'expenses_other': expenses_other,
                    'expenses_total': expenses_total,
                    'net_profit': net_profit,
                    'sales_count': sales_count,
                    'procurement_count': procurement_count,
                    'expense_count': expense_count,
                    'calculated_at': timezone.now(),
                }
            )
            action = 'Created' if created else 'Updated'
            self._info(f'  {action} summary record.')

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
        """Calculate operational expenses (utilities, salaries, etc.)."""
        result = Expense.objects.filter(
            status='APPROVED',
            date__gte=start_date,
            date__lt=end_date,
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

    def _info(self, msg):
        """Print info message unless quiet mode."""
        if not self.quiet:
            self.stdout.write(msg)
