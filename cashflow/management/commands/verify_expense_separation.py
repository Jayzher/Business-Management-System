"""
Management command: verify_expense_separation
==============================================
Verifies that operational expenses correctly exclude COGS/procurement expenses.

Usage:
    python manage.py verify_expense_separation
    python manage.py verify_expense_separation --year 2026 --month 4
"""
from decimal import Decimal
from datetime import date

from django.core.management.base import BaseCommand
from django.db.models import Sum, Q

from core.models import Expense, ExpenseCategory
from cashflow.models import MonthlyCashflowSummary


class Command(BaseCommand):
    help = 'Verify that operational expenses correctly exclude COGS/procurement expenses'

    def add_arguments(self, parser):
        parser.add_argument(
            '--year',
            type=int,
            help='Check specific year (default: current year)',
        )
        parser.add_argument(
            '--month',
            type=int,
            help='Check specific month (1-12, requires --year)',
        )

    def handle(self, *args, **options):
        year = options.get('year') or date.today().year
        month = options.get('month')

        self.stdout.write(self.style.SUCCESS('\n=== Expense Separation Verification ===\n'))

        # First, check expense categories configuration
        self._check_expense_categories()

        # Then check specific month or all months
        if month:
            self._check_month(year, month)
        else:
            # Check all months in the year
            summaries = MonthlyCashflowSummary.objects.filter(year=year).order_by('month')
            if not summaries:
                self.stdout.write(self.style.WARNING(f'No monthly summaries found for {year}'))
                return

            for summary in summaries:
                self._check_month(summary.year, summary.month)

    def _check_expense_categories(self):
        """Check expense category configuration."""
        self.stdout.write(self.style.SUCCESS('\n--- Expense Category Configuration ---'))

        categories = ExpenseCategory.objects.all().order_by('name')
        if not categories:
            self.stdout.write(self.style.WARNING('No expense categories found!'))
            return

        cogs_categories = []
        operational_categories = []

        for cat in categories:
            if cat.is_cogs:
                cogs_categories.append(cat.name)
            else:
                operational_categories.append(cat.name)

        self.stdout.write(f'\n✅ COGS/Procurement Categories ({len(cogs_categories)}):')
        for name in cogs_categories:
            self.stdout.write(f'   - {name}')

        self.stdout.write(f'\n✅ Operational Categories ({len(operational_categories)}):')
        for name in operational_categories:
            self.stdout.write(f'   - {name}')

        if not cogs_categories:
            self.stdout.write(self.style.WARNING('\n⚠️  No COGS categories found! Set is_cogs=True for procurement-related categories.'))

    def _check_month(self, year, month):
        """Check expense separation for a specific month."""
        from calendar import month_name

        self.stdout.write(self.style.SUCCESS(f'\n--- {month_name[month]} {year} ---'))

        # Date range
        if month == 12:
            next_month = date(year + 1, 1, 1)
        else:
            next_month = date(year, month + 1, 1)
        start_date = date(year, month, 1)
        end_date = next_month

        # Get all expenses for this month
        all_expenses = Expense.objects.filter(
            status='APPROVED',
            date__gte=start_date,
            date__lt=end_date,
        )

        # Get COGS expenses
        cogs_expenses = all_expenses.filter(category__is_cogs=True)

        # Get operational expenses
        operational_expenses = all_expenses.filter(category__is_cogs=False)

        # Calculate totals
        total_all = all_expenses.aggregate(total=Sum('amount'))['total'] or Decimal('0')
        total_cogs = cogs_expenses.aggregate(total=Sum('amount'))['total'] or Decimal('0')
        total_operational = operational_expenses.aggregate(total=Sum('amount'))['total'] or Decimal('0')

        # Get summary
        try:
            summary = MonthlyCashflowSummary.objects.get(year=year, month=month)
            summary_operational = summary.expenses_operational
        except MonthlyCashflowSummary.DoesNotExist:
            summary = None
            summary_operational = Decimal('0')

        # Display results
        self.stdout.write(f'\n📊 Expense Breakdown:')
        self.stdout.write(f'   All Expenses:         ₱{total_all:,.2f} ({all_expenses.count()} records)')
        self.stdout.write(f'   COGS Expenses:        ₱{total_cogs:,.2f} ({cogs_expenses.count()} records)')
        self.stdout.write(f'   Operational Expenses: ₱{total_operational:,.2f} ({operational_expenses.count()} records)')

        # Verify math
        calculated_total = total_cogs + total_operational
        if abs(calculated_total - total_all) > Decimal('0.01'):
            self.stdout.write(self.style.ERROR(f'\n❌ ERROR: COGS + Operational ({calculated_total:,.2f}) != Total ({total_all:,.2f})'))
        else:
            self.stdout.write(self.style.SUCCESS(f'\n✅ Math Check: COGS + Operational = Total'))

        # Check summary
        if summary:
            self.stdout.write(f'\n📋 Monthly Summary:')
            self.stdout.write(f'   Stored Operational:   ₱{summary_operational:,.2f}')

            if abs(summary_operational - total_operational) > Decimal('0.01'):
                self.stdout.write(self.style.ERROR(f'\n❌ MISMATCH: Summary operational ({summary_operational:,.2f}) != Calculated ({total_operational:,.2f})'))
                self.stdout.write(self.style.WARNING(f'   Run: python manage.py calculate_monthly_cashflow --year {year} --month {month}'))
            else:
                self.stdout.write(self.style.SUCCESS(f'✅ Summary matches calculated operational expenses'))
        else:
            self.stdout.write(self.style.WARNING(f'\n⚠️  No monthly summary found. Run: python manage.py calculate_monthly_cashflow --year {year} --month {month}'))

        # Show expense details if there are any
        if cogs_expenses.exists():
            self.stdout.write(f'\n💰 COGS Expenses:')
            for exp in cogs_expenses[:5]:  # Show first 5
                self.stdout.write(f'   - {exp.date} | {exp.category.name} | ₱{exp.amount:,.2f} | {exp.vendor or "N/A"}')
            if cogs_expenses.count() > 5:
                self.stdout.write(f'   ... and {cogs_expenses.count() - 5} more')

        if operational_expenses.exists():
            self.stdout.write(f'\n🏢 Operational Expenses:')
            for exp in operational_expenses[:5]:  # Show first 5
                self.stdout.write(f'   - {exp.date} | {exp.category.name} | ₱{exp.amount:,.2f} | {exp.vendor or "N/A"}')
            if operational_expenses.count() > 5:
                self.stdout.write(f'   ... and {operational_expenses.count() - 5} more')

        # Final verdict
        if summary and abs(summary_operational - total_operational) < Decimal('0.01'):
            self.stdout.write(self.style.SUCCESS(f'\n✅ {month_name[month]} {year}: Expense separation is CORRECT'))
        else:
            self.stdout.write(self.style.WARNING(f'\n⚠️  {month_name[month]} {year}: Needs recalculation'))

        self.stdout.write('\n' + '-' * 60)
