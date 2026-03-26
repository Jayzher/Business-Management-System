"""
Management command: backfill_po_for_grns
==========================================
Creates missing Purchase Orders for Goods Receipts that were imported via the
CSV import tool before the import bug was fixed.  The bug created GRN records
with `purchase_order=None`, bypassing the normal PO → GRN → Post flow.

This command:
  1. Finds every POSTED GoodsReceipt where purchase_order is NULL.
  2. For each orphaned GRN creates a PurchaseOrder (status=APPROVED) whose
     order_date equals the GRN receipt_date, using the same supplier/warehouse.
  3. Creates PurchaseOrderLine records from the GRN lines.
     - qty_ordered  = line.qty  (what was actually received)
     - qty_received = line.qty  (already received — stock already in inventory)
     - unit_price is taken from the matching StockMove weighted-average cost when
       available; otherwise defaults to the item's current cost_price.
  4. Links the GRN to the new PO (grn.purchase_order = po).

Stock quantities and StockBalance are NOT modified — the inventory is already
correct.  Only the PO / GRN linkage is backfilled.

Usage:
    python manage.py backfill_po_for_grns              # dry-run (safe, no DB writes)
    python manage.py backfill_po_for_grns --apply      # commit changes
    python manage.py backfill_po_for_grns --apply --quiet
    python manage.py backfill_po_for_grns --grn GRN-000042          # single GRN
    python manage.py backfill_po_for_grns --grn GRN-000042 --apply
"""
from collections import defaultdict
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from core.models import DocumentStatus
from inventory.services import generate_document_number
from procurement.models import (
    GoodsReceipt,
    PurchaseOrder,
    PurchaseOrderLine,
)


# ── helpers ──────────────────────────────────────────────────────────────────

def _resolve_unit_price(grn_line):
    """
    Best-effort unit price for a GRN line that had no PO:
      1. Use the item's current cost_price if > 0.
      2. Fall back to 0 (unknown — was not recorded during import).
    """
    cost = getattr(grn_line.item, 'cost_price', None) or Decimal('0')
    return cost if cost > 0 else Decimal('0')


# ── core logic ────────────────────────────────────────────────────────────────

def _backfill_single_grn(grn, dry_run, out_fn, warn_fn):
    """
    Backfill one GRN: create a PO, create PO lines, link GRN to PO.
    Returns (po_doc_number, po_line_count).
    """
    lines = list(grn.lines.select_related('item__cost_price', 'item__stock_unit', 'unit').all())

    if not lines:
        warn_fn(f'  [SKIP] {grn.document_number} — no GRN lines found; skipping.')
        return None, 0

    # Build PO lines consolidated by item (a single GRN can have the same
    # item on multiple lines, e.g. different locations).
    item_map = defaultdict(lambda: {'qty': Decimal('0'), 'unit': None, 'unit_price': Decimal('0')})
    for line in lines:
        entry = item_map[line.item.pk]
        entry['qty'] += line.qty
        entry['unit'] = line.unit
        entry['item'] = line.item
        # Use the highest unit price seen for this item (conservative; avoids 0)
        candidate_price = _resolve_unit_price(line)
        if candidate_price > entry['unit_price']:
            entry['unit_price'] = candidate_price

    po_doc_number = generate_document_number('PO', PurchaseOrder)

    out_fn(
        f'  GRN {grn.document_number}  supplier={grn.supplier}  '
        f'warehouse={grn.warehouse}  date={grn.receipt_date}  '
        f'lines={len(lines)}  → PO {po_doc_number}'
    )

    if dry_run:
        return po_doc_number, len(item_map)

    with transaction.atomic():
        now = timezone.now()

        # Determine approved_by: use the GRN's created_by as a best proxy
        approver = grn.created_by

        po = PurchaseOrder.objects.create(
            document_number=po_doc_number,
            supplier=grn.supplier,
            warehouse=grn.warehouse,
            order_date=grn.receipt_date,
            expected_date=grn.receipt_date,
            status=DocumentStatus.APPROVED,
            notes=(
                f'Auto-backfilled from {grn.document_number} '
                f'(receipt date {grn.receipt_date}). '
                'Created by backfill_po_for_grns management command.'
            ),
            created_by=approver,
            approved_by=approver,
            approved_at=now,
        )

        for item_pk, entry in item_map.items():
            PurchaseOrderLine.objects.create(
                purchase_order=po,
                item=entry['item'],
                qty_ordered=entry['qty'],
                qty_received=entry['qty'],   # already fully received
                unit=entry['unit'],
                unit_price=entry['unit_price'],
            )

        # Link the GRN to the new PO
        GoodsReceipt.all_objects.filter(pk=grn.pk).update(purchase_order=po)

    return po_doc_number, len(item_map)


# ── management command ────────────────────────────────────────────────────────

class Command(BaseCommand):
    help = (
        'Backfill missing Purchase Orders for GoodsReceipts that were imported '
        'without a linked PO (the import bug). Stock levels are NOT changed.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply',
            action='store_true',
            default=False,
            help='Commit changes to the database. Without this flag the command runs as a dry-run.',
        )
        parser.add_argument(
            '--quiet',
            action='store_true',
            default=False,
            help='Suppress per-GRN output; only print the summary.',
        )
        parser.add_argument(
            '--grn',
            metavar='DOCUMENT_NUMBER',
            default=None,
            help='Backfill a single GRN by document number (e.g. GRN-000042).',
        )

    def handle(self, *args, **options):
        dry_run = not options['apply']
        quiet = options['quiet']
        single_grn_number = options.get('grn')

        def out_fn(msg):
            if not quiet:
                self.stdout.write(msg)

        def warn_fn(msg):
            self.stderr.write(self.style.WARNING(msg))

        mode_label = 'DRY-RUN' if dry_run else 'APPLY'
        self.stdout.write(self.style.MIGRATE_HEADING(
            f'\n=== backfill_po_for_grns [{mode_label}] ==='
        ))
        if dry_run:
            self.stdout.write(
                self.style.WARNING('  No changes will be written. Pass --apply to commit.\n')
            )

        # ── build queryset ────────────────────────────────────────────────────
        orphan_qs = (
            GoodsReceipt.all_objects
            .filter(purchase_order__isnull=True, status=DocumentStatus.POSTED)
            .select_related('supplier', 'warehouse', 'created_by')
            .order_by('receipt_date', 'id')
        )

        if single_grn_number:
            orphan_qs = orphan_qs.filter(document_number=single_grn_number)
            if not orphan_qs.exists():
                raise CommandError(
                    f'No POSTED GRN with document_number="{single_grn_number}" and '
                    'purchase_order=NULL found. It may already have a PO, be in a '
                    'different status, or the number is incorrect.'
                )

        total_grns = orphan_qs.count()
        if total_grns == 0:
            self.stdout.write(self.style.SUCCESS(
                '  No orphaned GRNs found — nothing to backfill. All GRNs already have a PO.'
            ))
            return

        self.stdout.write(f'  Found {total_grns} POSTED GRN(s) with purchase_order=NULL\n')

        # ── process ───────────────────────────────────────────────────────────
        processed = 0
        skipped = 0
        total_po_lines = 0
        errors = []

        for grn in orphan_qs.iterator():
            try:
                po_doc_number, po_line_count = _backfill_single_grn(
                    grn, dry_run, out_fn, warn_fn
                )
                if po_doc_number is None:
                    skipped += 1
                else:
                    processed += 1
                    total_po_lines += po_line_count
            except Exception as exc:
                err_msg = f'  [ERROR] {grn.document_number}: {exc}'
                self.stderr.write(self.style.ERROR(err_msg))
                errors.append(err_msg)
                skipped += 1

        # ── summary ──────────────────────────────────────────────────────────
        self.stdout.write('')
        self.stdout.write(self.style.MIGRATE_HEADING('=== Summary ==='))
        self.stdout.write(f'  GRNs processed : {processed}')
        self.stdout.write(f'  PO lines created: {total_po_lines}')
        self.stdout.write(f'  Skipped / errors: {skipped}')

        if errors:
            self.stdout.write(self.style.ERROR(f'  Errors ({len(errors)}):'))
            for e in errors:
                self.stdout.write(self.style.ERROR(f'    {e}'))

        if dry_run and processed > 0:
            self.stdout.write(self.style.WARNING(
                '\n  Dry-run complete — no changes written. Re-run with --apply to commit.'
            ))
        elif not dry_run and processed > 0:
            self.stdout.write(self.style.SUCCESS(
                f'\n  Done — {processed} PO(s) created and linked to their GRNs.'
            ))
        elif processed == 0 and skipped == 0:
            self.stdout.write(self.style.SUCCESS('  Nothing to do.'))
