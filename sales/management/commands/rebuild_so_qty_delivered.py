"""
Management command: rebuild_so_qty_delivered

Recomputes SalesOrderLine.qty_delivered by replaying the exact item-matching
algorithm used by inventory.services.post_sales_pickup / post_delivery
(the same one inventory.management.commands.resync_inventory's Phase 1c
uses via _pick_so_line) against every POSTED SalesPickup/DeliveryNote linked
to each targeted Sales Order, in posted_at order.

Why a separate, scoped command instead of just running
`resync_inventory --phase 1`: that command wraps its ENTIRE run (Phase 0-2,
every SO in the system) in one all-or-nothing transaction, and aborts the
whole thing if ANY item anywhere in the catalog is missing a unit
conversion. As of 2026-07-16 there are 28 such items, unrelated to the SOs
this command targets, which makes the system-wide command a no-op until
someone supplies those conversion factors. This command only touches the
specific Sales Orders you pass in, and skips (rather than aborts on) a line
it can't convert — so it isn't blocked by unrelated catalog gaps.

Background: investigating INV-001417 (2026-07-16) found SO-000964 with all
11 lines stuck at qty_delivered=0 despite a posted pickup (PU-001029) with
matching StockMoves — because _create_invoice_lines_from_so() skips any SO
line with qty_delivered <= 0, a later resync of the invoice from the SO
silently dropped all 11 items, shrinking the invoice below a payment already
recorded against it. A DB sweep found 9 invoices with total_paid >
grand_total; 8 are SO-linked and are this command's default target list.

Usage:
  python manage.py rebuild_so_qty_delivered                  # dry run, default SO list
  python manage.py rebuild_so_qty_delivered --so SO-000964    # dry run, specific SO(s)
  python manage.py rebuild_so_qty_delivered --apply           # persist + resync linked invoices
"""
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from core.models import DocumentStatus
from sales.models import SalesOrder

# The 8 SO-linked invoices found with total_paid > grand_total as of the
# 2026-07-16 investigation (a 9th affected invoice, 001144, has no linked
# Sales Order and can't be fixed by this command).
DEFAULT_SO_NUMBERS = [
    'SO-000964', 'SO-000959', 'SO-000920', 'SO-000757',
    'SO-000666', 'SO-000449', 'SO-000369', '063-03/11/2026',
]


def replay_qty_delivered(so):
    """
    Return {so_line_pk: recomputed_qty_delivered} for `so`, replaying the same
    matching algorithm as inventory.services.post_sales_pickup/post_delivery
    (inventory.services._pick_so_line) against every POSTED pickup/delivery
    linked to this SO, oldest first.
    """
    from inventory.services import _pick_so_line, _convert_qty_safe, is_bundle_component_line

    computed = {sl.pk: Decimal('0') for sl in so.lines.all()}

    docs = list(so.pickups.filter(status=DocumentStatus.POSTED)) + \
        list(so.deliveries.filter(status=DocumentStatus.POSTED))
    docs.sort(key=lambda d: d.posted_at or d.created_at)

    for doc in docs:
        for line in doc.lines.select_related('item', 'unit').all():
            # Bundle-component lines are billed via a separate BUNDLE invoice
            # line and must not count toward any flat SO line's qty_delivered.
            if is_bundle_component_line(line):
                continue
            so_line = _pick_so_line(so, line.item, line.unit)
            if so_line is None:
                continue
            if so_line.unit_id == line.unit_id:
                delivered = line.qty
            else:
                delivered = _convert_qty_safe(line.qty, line.unit, so_line.unit, line.item) or Decimal('0')
            computed[so_line.pk] = computed.get(so_line.pk, Decimal('0')) + delivered

    return computed


class Command(BaseCommand):
    help = (
        'Recompute SalesOrderLine.qty_delivered for specific Sales Orders by '
        'replaying their posted pickups/deliveries through the same '
        'matching algorithm the live posting code uses. Scoped (not '
        'system-wide) so it is not blocked by unrelated catalog data gaps. '
        'Dry-run by default; pass --apply to persist and resync linked '
        'invoices.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--so', dest='so_numbers', nargs='+', default=None,
            help='Sales Order document number(s) to process. Defaults to the '
                 '8 SOs found linked to overpaid invoices in the 2026-07-16 '
                 'investigation.',
        )
        parser.add_argument(
            '--apply', action='store_true',
            help='Persist corrected qty_delivered values and resync linked '
                 'invoices. Without this flag, only a diff report is printed.',
        )

    def handle(self, *args, **options):
        from sales.models import SalesOrderLine
        from core.models import Invoice
        from inventory.automation import sync_invoice_totals_from_so

        so_numbers = options.get('so_numbers') or DEFAULT_SO_NUMBERS
        apply_changes = options.get('apply')

        qs = SalesOrder.objects.filter(document_number__in=so_numbers).prefetch_related('lines')
        found_numbers = set(qs.values_list('document_number', flat=True))
        missing = set(so_numbers) - found_numbers
        if missing:
            self.stdout.write(self.style.WARNING(
                f'Not found, skipping: {", ".join(sorted(missing))}'
            ))

        total_lines_changed = 0
        sos_changed = []  # (so, [(line, old, new), ...])

        for so in qs:
            computed = replay_qty_delivered(so)
            line_diffs = [
                (sl, sl.qty_delivered, computed.get(sl.pk, Decimal('0')))
                for sl in so.lines.all()
                if computed.get(sl.pk, Decimal('0')) != (sl.qty_delivered or Decimal('0'))
            ]
            if not line_diffs:
                self.stdout.write(f'\n{so.document_number}: no drift.')
                continue

            sos_changed.append((so, line_diffs))
            self.stdout.write(f'\n{so.document_number}:')
            for sl, old_val, new_val in line_diffs:
                flag = '  <- exceeds qty_ordered' if new_val > sl.qty_ordered else ''
                self.stdout.write(
                    f'  line {sl.pk} ({sl.item.code}): '
                    f'qty_delivered {old_val} -> {new_val} (qty_ordered={sl.qty_ordered}){flag}'
                )
                total_lines_changed += 1

        if not sos_changed:
            self.stdout.write(self.style.SUCCESS('\nNo qty_delivered drift found.'))
            return

        self.stdout.write(
            f'\n{len(sos_changed)} Sales Order(s), {total_lines_changed} line(s) would change.'
        )

        if not apply_changes:
            self.stdout.write(self.style.WARNING(
                '\nDry run — no changes made. Re-run with --apply to persist.'
            ))
            return

        with transaction.atomic():
            for so, line_diffs in sos_changed:
                for sl, _old_val, new_val in line_diffs:
                    sl.qty_delivered = new_val
                SalesOrderLine.objects.bulk_update(
                    [sl for sl, _o, _n in line_diffs], ['qty_delivered']
                )
                for invoice in Invoice.objects.filter(sales_order=so, is_void=False):
                    sync_invoice_totals_from_so(invoice, so, count_new_lines=False)

        self.stdout.write(self.style.SUCCESS(
            f'\nApplied. {len(sos_changed)} Sales Order(s) corrected and linked invoices resynced.'
        ))
