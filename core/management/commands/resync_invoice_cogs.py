"""
Management command: resync_invoice_cogs

Recompute grand_total_cogs on selected invoices using the CURRENT
Item.cost_price values, then cascade-update the affected monthly
cashflow summaries so that inventory value and P&L are corrected.

Use this after you've updated cost prices on catalog items and need
those new costs reflected in past invoices.

Usage examples:
  # Resync ALL invoices and rebuild affected monthly summaries
  python manage.py resync_invoice_cogs --all

  # Resync invoices in a date range
  python manage.py resync_invoice_cogs --from 2026-01-01 --to 2026-01-31

  # Resync specific invoices by number
  python manage.py resync_invoice_cogs --invoices 000123 000124 000130

  # Resync specific invoices by PK
  python manage.py resync_invoice_cogs --pks 42 43 50

  # Preview without saving
  python manage.py resync_invoice_cogs --all --dry-run
"""
from datetime import date as _date
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError

from core.cogs import compute_invoice_cogs
from core.models import Invoice


class Command(BaseCommand):
    help = (
        'Resync grand_total_cogs on selected invoices using current '
        'Item.cost_price, then rebuild affected monthly cashflow summaries.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--all', action='store_true',
            help='Resync ALL invoices.',
        )
        parser.add_argument(
            '--from', dest='date_from', type=str, default=None,
            help='Start date (YYYY-MM-DD). Used with --to for a date range.',
        )
        parser.add_argument(
            '--to', dest='date_to', type=str, default=None,
            help='End date (YYYY-MM-DD). Used with --from for a date range.',
        )
        parser.add_argument(
            '--invoices', nargs='+', type=str, default=None,
            help='One or more invoice numbers to resync.',
        )
        parser.add_argument(
            '--pks', nargs='+', type=int, default=None,
            help='One or more invoice PKs to resync.',
        )
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Print what would change without saving.',
        )
        parser.add_argument(
            '--skip-monthly', action='store_true',
            help='Skip monthly cashflow summary recalculation.',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        skip_monthly = options['skip_monthly']
        do_all = options['all']
        date_from = options['date_from']
        date_to = options['date_to']
        invoice_numbers = options['invoices']
        invoice_pks = options['pks']

        # ── Validate arguments ────────────────────────────────────────────
        selectors = sum([
            bool(do_all),
            bool(date_from or date_to),
            bool(invoice_numbers),
            bool(invoice_pks),
        ])
        if selectors == 0:
            raise CommandError(
                'Specify at least one selector: --all, --from/--to, '
                '--invoices, or --pks.'
            )
        if selectors > 1:
            raise CommandError(
                'Use only one selector at a time: --all, --from/--to, '
                '--invoices, or --pks.'
            )

        # ── Build queryset ────────────────────────────────────────────────
        qs = Invoice.objects.select_related('pos_sale', 'sales_order')

        if do_all:
            pass  # no filter
        elif date_from or date_to:
            if date_from:
                try:
                    d = _date.fromisoformat(date_from)
                except ValueError:
                    raise CommandError(f'Invalid --from date: {date_from}')
                qs = qs.filter(date__gte=d)
            if date_to:
                try:
                    d = _date.fromisoformat(date_to)
                except ValueError:
                    raise CommandError(f'Invalid --to date: {date_to}')
                qs = qs.filter(date__lte=d)
        elif invoice_numbers:
            qs = qs.filter(invoice_number__in=invoice_numbers)
        elif invoice_pks:
            qs = qs.filter(pk__in=invoice_pks)

        invoices = list(qs.order_by('date', 'pk'))
        if not invoices:
            self.stdout.write(self.style.WARNING('No invoices matched the selection.'))
            return

        self.stdout.write(f'\nFound {len(invoices)} invoice(s) to resync.\n')

        # ── Resync COGS ──────────────────────────────────────────────────
        updated = 0
        skipped = 0
        errors = 0
        affected_months = set()

        for inv in invoices:
            try:
                new_cogs = compute_invoice_cogs(inv)
            except Exception as e:
                self.stderr.write(
                    self.style.ERROR(
                        f'  [ERROR] INV {inv.invoice_number}: {e}'
                    )
                )
                errors += 1
                continue

            old_cogs = inv.grand_total_cogs or Decimal('0')
            changed = old_cogs != new_cogs

            if dry_run:
                marker = ' *CHANGED*' if changed else ''
                self.stdout.write(
                    f'  INV {inv.invoice_number:<20} '
                    f'date={inv.date}  '
                    f'old_cogs={old_cogs:>12,.2f}  '
                    f'new_cogs={new_cogs:>12,.2f}'
                    f'{marker}'
                )
                if changed:
                    updated += 1
                else:
                    skipped += 1
            else:
                if changed:
                    inv.grand_total_cogs = new_cogs
                    inv.save(update_fields=['grand_total_cogs'])
                    self.stdout.write(
                        f'  ✓ INV {inv.invoice_number}  '
                        f'{old_cogs:>12,.2f} → {new_cogs:>12,.2f}'
                    )
                    updated += 1
                else:
                    skipped += 1

            # Track affected months for summary recalculation
            if inv.date and changed:
                affected_months.add((inv.date.year, inv.date.month))

        # ── Summary ───────────────────────────────────────────────────────
        self.stdout.write('')
        if dry_run:
            self.stdout.write(
                self.style.SUCCESS(
                    f'Dry-run complete: {updated} would change, '
                    f'{skipped} already correct, {errors} errors.'
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f'COGS resync complete: {updated} updated, '
                    f'{skipped} already correct, {errors} errors.'
                )
            )

        # ── Rebuild affected monthly summaries ────────────────────────────
        if not dry_run and not skip_monthly and affected_months:
            self.stdout.write(
                f'\nRecalculating {len(affected_months)} affected monthly '
                f'summary(ies)...'
            )
            from cashflow.monthly_signals import update_monthly_summary

            for year, month in sorted(affected_months):
                try:
                    update_monthly_summary(year, month)
                    self.stdout.write(
                        f'  ✓ {year}-{month:02d} summary updated'
                    )
                except Exception as e:
                    self.stderr.write(
                        self.style.ERROR(
                            f'  [ERROR] {year}-{month:02d}: {e}'
                        )
                    )

            self.stdout.write(
                self.style.SUCCESS(
                    'Monthly summaries rebuilt (cascades to subsequent months automatically).'
                )
            )
        elif dry_run and affected_months:
            self.stdout.write(
                f'\nWould recalculate monthly summaries for: '
                + ', '.join(
                    f'{y}-{m:02d}' for y, m in sorted(affected_months)
                )
            )
