"""
Management command: rebuild_cashflow_balances

Rebuilds all monthly cashflow summaries in chronological order to properly
backfill opening and closing balances. This ensures that:
1. Each month's opening balance comes from the previous month's closing
2. Balances cascade correctly through all months
3. Any missing months are created
4. All calculations are up-to-date

Usage:
  python manage.py rebuild_cashflow_balances                    # All months
  python manage.py rebuild_cashflow_balances --year 2026        # Specific year
  python manage.py rebuild_cashflow_balances --from 2025-01     # From specific month
  python manage.py rebuild_cashflow_balances --dry-run          # Preview without saving
"""
from django.core.management.base import BaseCommand
from django.db.models import Min, Max
from cashflow.models import MonthlyCashflowSummary
from cashflow.monthly_signals import update_monthly_summary
from datetime import date
from decimal import Decimal


class Command(BaseCommand):
    help = 'Rebuild all monthly cashflow summaries with proper opening/closing balances'

    def add_arguments(self, parser):
        parser.add_argument(
            '--year',
            type=int,
            help='Rebuild only this specific year',
        )
        parser.add_argument(
            '--from',
            type=str,
            dest='from_month',
            help='Rebuild from this month forward (format: YYYY-MM)',
        )
        parser.add_argument(
            '--to',
            type=str,
            dest='to_month',
            help='Rebuild up to this month (format: YYYY-MM)',
        )
        parser.add_argument(
            '--set-opening',
            type=float,
            dest='set_opening',
            help='Set the opening balance for the first month (default: 0)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without actually updating',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        year_filter = options.get('year')
        from_month = options.get('from_month')
        to_month = options.get('to_month')
        set_opening_value = options.get('set_opening')
        set_opening = Decimal(str(set_opening_value)) if set_opening_value is not None else Decimal('0')

        self.stdout.write('=' * 70)
        self.stdout.write(self.style.SUCCESS('Cashflow Balance Rebuild'))
        if dry_run:
            self.stdout.write(self.style.WARNING('*** DRY RUN - No changes will be saved ***'))
        self.stdout.write('=' * 70)

        # Determine date range
        start_year, start_month, end_year, end_month = self._determine_date_range(
            year_filter, from_month, to_month
        )

        if not start_year:
            self.stdout.write(self.style.ERROR('No data found to rebuild'))
            return

        self.stdout.write(f'\nRebuilding from {start_year}-{start_month:02d} to {end_year}-{end_month:02d}')
        if set_opening != 0:
            self.stdout.write(f'Setting opening balance for first month: ₱{set_opening:,.2f}')
        self.stdout.write('')

        # Generate list of all months to process
        months_to_process = self._generate_month_list(
            start_year, start_month, end_year, end_month
        )

        self.stdout.write(f'Total months to process: {len(months_to_process)}\n')

        # Process each month in chronological order
        previous_closing = set_opening
        updated_count = 0
        created_count = 0
        skipped_count = 0

        for year, month in months_to_process:
            try:
                # Check if summary exists
                try:
                    summary = MonthlyCashflowSummary.objects.get(year=year, month=month)
                    existed = True
                except MonthlyCashflowSummary.DoesNotExist:
                    summary = None
                    existed = False

                # Calculate what the opening balance should be
                expected_opening = previous_closing

                if dry_run:
                    # Just show what would happen
                    if existed:
                        self.stdout.write(
                            f'  {year}-{month:02d}: Would update '
                            f'(current opening: ₱{summary.opening_balance:,.2f}, '
                            f'expected: ₱{expected_opening:,.2f})'
                        )
                        # Calculate what closing would be
                        net_flow = summary.total_inflow - summary.total_outflow
                        expected_closing = expected_opening + net_flow
                        previous_closing = expected_closing
                    else:
                        self.stdout.write(
                            f'  {year}-{month:02d}: Would create new summary '
                            f'(opening: ₱{expected_opening:,.2f})'
                        )
                        previous_closing = expected_opening  # Assume 0 net flow for missing months
                else:
                    # Actually update/create the summary
                    # Temporarily disable cascade to prevent infinite loops
                    summary = update_monthly_summary(year, month, user=None)
                    
                    # Manually set the opening balance if it's different
                    if summary.opening_balance != expected_opening:
                        summary.opening_balance = expected_opening
                        # Recalculate closing balance
                        summary.closing_balance = expected_opening + summary.net_cash_flow
                        summary.save(update_fields=['opening_balance', 'closing_balance'])
                    
                    if existed:
                        self.stdout.write(
                            self.style.SUCCESS(
                                f'  ✓ {year}-{month:02d}: Updated '
                                f'(opening: ₱{summary.opening_balance:,.2f}, '
                                f'closing: ₱{summary.closing_balance:,.2f}, '
                                f'net flow: ₱{summary.net_cash_flow:,.2f})'
                            )
                        )
                        updated_count += 1
                    else:
                        self.stdout.write(
                            self.style.SUCCESS(
                                f'  ✓ {year}-{month:02d}: Created '
                                f'(opening: ₱{summary.opening_balance:,.2f}, '
                                f'closing: ₱{summary.closing_balance:,.2f})'
                            )
                        )
                        created_count += 1
                    
                    # Set previous closing for next iteration
                    previous_closing = summary.closing_balance

            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'  ✗ {year}-{month:02d}: Error - {e}')
                )
                skipped_count += 1
                continue

        # Summary
        self.stdout.write('\n' + '=' * 70)
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN COMPLETE - No changes were made'))
        else:
            self.stdout.write(self.style.SUCCESS('REBUILD COMPLETE'))
            self.stdout.write(f'  Created: {created_count}')
            self.stdout.write(f'  Updated: {updated_count}')
            if skipped_count > 0:
                self.stdout.write(self.style.WARNING(f'  Skipped (errors): {skipped_count}'))
        self.stdout.write('=' * 70)

    def _determine_date_range(self, year_filter, from_month, to_month):
        """Determine the start and end dates for rebuilding."""
        from pos.models import POSSale
        from core.models import Invoice, Expense
        from procurement.models import GoodsReceipt
        
        # If specific year provided
        if year_filter:
            return year_filter, 1, year_filter, 12
        
        # If from_month provided
        if from_month:
            try:
                year, month = map(int, from_month.split('-'))
                start_year, start_month = year, month
            except ValueError:
                self.stdout.write(self.style.ERROR(f'Invalid from_month format: {from_month}'))
                return None, None, None, None
        else:
            # Find earliest transaction date across all sources
            earliest_dates = []
            
            # Check POS sales
            pos_earliest = POSSale.objects.filter(status='POSTED').aggregate(Min('created_at'))
            if pos_earliest['created_at__min']:
                earliest_dates.append(pos_earliest['created_at__min'])
            
            # Check invoices
            inv_earliest = Invoice.objects.filter(is_void=False).aggregate(Min('paid_at'))
            if inv_earliest['paid_at__min']:
                earliest_dates.append(inv_earliest['paid_at__min'])
            
            # Check expenses
            exp_earliest = Expense.objects.filter(status='APPROVED').aggregate(Min('date'))
            if exp_earliest['date__min']:
                earliest_dates.append(exp_earliest['date__min'])
            
            # Check GRNs
            grn_earliest = GoodsReceipt.objects.filter(status='POSTED').aggregate(Min('receipt_date'))
            if grn_earliest['receipt_date__min']:
                earliest_dates.append(grn_earliest['receipt_date__min'])
            
            if not earliest_dates:
                # No data found, use current month
                today = date.today()
                start_year, start_month = today.year, today.month
            else:
                earliest = min(earliest_dates)
                start_year, start_month = earliest.year, earliest.month
        
        # If to_month provided
        if to_month:
            try:
                year, month = map(int, to_month.split('-'))
                end_year, end_month = year, month
            except ValueError:
                self.stdout.write(self.style.ERROR(f'Invalid to_month format: {to_month}'))
                return None, None, None, None
        else:
            # Use current month as end
            today = date.today()
            end_year, end_month = today.year, today.month
        
        return start_year, start_month, end_year, end_month

    def _generate_month_list(self, start_year, start_month, end_year, end_month):
        """Generate a list of (year, month) tuples in chronological order."""
        months = []
        current_year = start_year
        current_month = start_month
        
        while (current_year < end_year) or (current_year == end_year and current_month <= end_month):
            months.append((current_year, current_month))
            
            # Move to next month
            if current_month == 12:
                current_month = 1
                current_year += 1
            else:
                current_month += 1
        
        return months
