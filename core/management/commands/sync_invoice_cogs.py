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
from decimal import Decimal

from django.core.management.base import BaseCommand

from core.models import Invoice


def _pos_cogs(pos_sale):
    """COGS from POS sale lines: item.cost_price × qty."""
    total = Decimal('0')
    for line in pos_sale.lines.select_related('item').all():
        total += (line.item.cost_price or Decimal('0')) * line.qty
    return total


def _so_cogs(sales_order):
    """COGS from SO lines + bundle lines."""
    total = Decimal('0')
    for line in sales_order.lines.select_related('item').all():
        total += (line.item.cost_price or Decimal('0')) * line.qty_ordered
    for bundle in sales_order.price_list_lines.prefetch_related(
        'price_list__items__item'
    ).all():
        for pli in bundle.price_list.items.all():
            total += (
                (pli.item.cost_price or Decimal('0'))
                * pli.min_qty
                * bundle.qty_multiplier
            )
    return total


def _service_cogs(invoice):
    """COGS from ServiceLine items linked to this invoice."""
    total = Decimal('0')
    for svc in invoice.customer_services.prefetch_related('lines__item').all():
        for line in svc.lines.all():
            total += (line.item.cost_price or Decimal('0')) * line.qty
    return total


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
            cogs = Decimal('0')

            if inv.pos_sale_id:
                try:
                    cogs = _pos_cogs(inv.pos_sale)
                except Exception as e:
                    self.stderr.write(
                        f'  [WARN] Invoice {inv.invoice_number} POS COGS error: {e}'
                    )

            elif inv.sales_order_id:
                try:
                    cogs = _so_cogs(inv.sales_order)
                except Exception as e:
                    self.stderr.write(
                        f'  [WARN] Invoice {inv.invoice_number} SO COGS error: {e}'
                    )

            # Services linked via FK on CustomerService → always add on top
            try:
                svc_cogs = _service_cogs(inv)
                cogs += svc_cogs
            except Exception as e:
                self.stderr.write(
                    f'  [WARN] Invoice {inv.invoice_number} Service COGS error: {e}'
                )

            cogs = cogs.quantize(Decimal('0.01'))

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
