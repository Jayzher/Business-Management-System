"""
Management command: sync_invoice_cogs

Iterates every Invoice and computes its COGS from the linked source document:
  - POS Sale    → sum(item.cost_price × qty) across POSSaleLine
  - Sales Order → sum(item.cost_price × qty_ordered) across SalesOrderLine
                  + sum(pli.item.cost_price × pli.min_qty × qty_multiplier)
                    across SalesOrderPriceListLine
  - Service     → sum(item.cost_price × qty) across ServiceLine
                  (uses CustomerService.invoice FK back-reference)

Usage:
  python manage.py sync_invoice_cogs              # all invoices
  python manage.py sync_invoice_cogs --invoice 42 # single invoice by PK
  python manage.py sync_invoice_cogs --dry-run    # print without saving
"""
from django.core.management.base import BaseCommand

from core.cogs import compute_invoice_cogs
from core.models import Invoice


class Command(BaseCommand):
    help = 'Sync grand_total_cogs on all (or a single) Invoice records.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--invoice', type=int, default=None,
            help='PK of a single invoice to sync (default: all).',
        )
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Print computed COGS without saving.',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        single_pk = options['invoice']

        qs = Invoice.objects.select_related('pos_sale', 'sales_order')
        if single_pk:
            qs = qs.filter(pk=single_pk)

        updated = 0
        skipped = 0

        for inv in qs.iterator():
            try:
                cogs = compute_invoice_cogs(inv)
            except Exception as e:
                self.stderr.write(
                    f'  [WARN] Invoice {inv.invoice_number} COGS error: {e}'
                )
                continue

            if dry_run:
                self.stdout.write(
                    f'  INV {inv.invoice_number:<20} '
                    f'revenue={inv.grand_total:>12,.2f}  '
                    f'cogs={cogs:>12,.2f}'
                )
                skipped += 1
            else:
                if inv.grand_total_cogs != cogs:
                    inv.grand_total_cogs = cogs
                    inv.save(update_fields=['grand_total_cogs'])
                    updated += 1
                else:
                    skipped += 1

        if dry_run:
            self.stdout.write(
                self.style.SUCCESS(f'Dry-run complete. {skipped} invoices inspected.')
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f'Sync complete. {updated} updated, {skipped} already correct.'
                )
            )
