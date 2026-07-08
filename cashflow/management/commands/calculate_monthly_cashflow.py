"""
Management command: calculate_monthly_cashflow
===============================================
Calculates or recalculates monthly cashflow summaries from all posted
transactions, sales, procurements, and expenses.

This command is a thin CLI wrapper around
cashflow.monthly_signals.update_monthly_summary() — the same function used
by the real-time post_save/post_delete signals. It used to duplicate that
calculation logic locally, but the two copies drifted apart (double-counted
POS revenue via linked invoices, capital_sales holding raw revenue instead
of gross profit, expenses_total including COGS, etc.). Delegating to a
single shared implementation makes that class of bug structurally
impossible going forward.

Usage:
    python manage.py calculate_monthly_cashflow                    # all months
    python manage.py calculate_monthly_cashflow --year 2024        # specific year
    python manage.py calculate_monthly_cashflow --year 2024 --month 3  # specific month
    python manage.py calculate_monthly_cashflow --dry-run          # preview only
"""
from django.core.management.base import BaseCommand
from django.db import transaction, router

from cashflow.models import CashFlowTransaction, CashFlowStatus
from cashflow.monthly_signals import update_monthly_summary
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
            periods = self._get_all_periods()

        if not periods:
            self.stdout.write(self.style.WARNING('No data found to calculate.'))
            return

        self.stdout.write(f'Calculating {len(periods)} month(s)...\n')

        # This project's local-first DB router can route all writes to a
        # 'local_cache' alias distinct from 'default'. A bare
        # transaction.atomic() only wraps 'default', so --dry-run's rollback
        # would silently no-op and commit real changes. Use the alias the
        # router actually writes to.
        write_db = router.db_for_write(CashFlowTransaction) or 'default'
        with transaction.atomic(using=write_db):
            for yr, mn in periods:
                self._calculate_month(yr, mn)

            if dry_run:
                transaction.set_rollback(True, using=write_db)
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

    def _calculate_month(self, year, month):
        """Calculate cashflow summary for a specific month via the shared helper."""
        from calendar import month_name

        self._info(f'\n--- {month_name[month]} {year} ---')

        summary = update_monthly_summary(year, month)

        self._info(f'  ┌─ BALANCE SHEET ──────────────────────────────────────────┐')
        self._info(f'  │ Opening Balance:          {self._fmt(summary.opening_balance):>20} │')
        self._info(f'  │   • Cash:                 {self._fmt(summary.cash_opening):>20} │')
        self._info(f'  │   • Inventory:            {self._fmt(summary.inventory_value_opening):>20} │')
        self._info(f'  │   • AR:                   {self._fmt(summary.accounts_receivable_opening):>20} │')
        self._info(f'  ├────────────────────────────────────────────────────────────┤')
        self._info(f'  │ Closing Balance:          {self._fmt(summary.closing_balance):>20} │')
        self._info(f'  │   • Cash:                 {self._fmt(summary.cash_closing):>20} │')
        self._info(f'  │   • Inventory:            {self._fmt(summary.inventory_value_closing):>20} │')
        self._info(f'  │   • AR:                   {self._fmt(summary.accounts_receivable_closing):>20} │')
        self._info(f'  └────────────────────────────────────────────────────────────┘')
        self._info(f'')
        self._info(f'  ┌─ CASH FLOW ───────────────────────────────────────────────┐')
        self._info(f'  │ Cash In:                                                   │')
        self._info(f'  │   From Customers:         {self._fmt(summary.cash_from_customers):>20} │')
        self._info(f'  │   Total Cash In:          {self._fmt(summary.total_inflow):>20} │')
        self._info(f'  │ Cash Out:                                                  │')
        self._info(f'  │   To Suppliers:           {self._fmt(summary.cash_to_suppliers):>20} │')
        self._info(f'  │   Operating Expenses:     {self._fmt(summary.expenses_operational):>20} │')
        self._info(f'  │   Other Cash Out:         {self._fmt(summary.expenses_other):>20} │')
        self._info(f'  │   Total Cash Out:         {self._fmt(summary.total_outflow):>20} │')
        self._info(f'  │ Net Cash Flow:            {self._fmt(summary.net_cash_flow):>20} │')
        self._info(f'  └────────────────────────────────────────────────────────────┘')
        self._info(f'')
        self._info(f'  ┌─ P&L ─────────────────────────────────────────────────────┐')
        self._info(f'  │ Revenue:                  {self._fmt(summary.revenue_accrual):>20} │')
        self._info(f'  │ COGS:                     {self._fmt(summary.cogs_actual):>20} │')
        self._info(f'  │ Gross Profit:             {self._fmt(summary.gross_profit):>20} │')
        self._info(f'  │ Gross Margin:             {summary.gross_margin_pct:>19.1f}% │')
        self._info(f'  │ Operating Expenses:       {self._fmt(summary.expenses_operational):>20} │')
        self._info(f'  │ Other Expenses:           {self._fmt(summary.expenses_other):>20} │')
        self._info(f'  │ Net Profit:               {self._fmt(summary.net_profit):>20} │')
        self._info(f'  └────────────────────────────────────────────────────────────┘')
        self._info(f'')
        self._info(
            f'  Transactions: {summary.sales_count} sales, '
            f'{summary.procurement_count} procurements, {summary.expense_count} expenses'
        )
        self._info(f'  Updated summary record.')

    def _fmt(self, amount):
        """Format currency amount."""
        return f'₱{amount:,.2f}'

    def _info(self, msg):
        """Print info message unless quiet mode."""
        if not self.quiet:
            self.stdout.write(msg)
