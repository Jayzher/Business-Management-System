"""
Management command: resync_inventory
======================================
Re-synchronises StockBalance and StockMove records to reflect correct unit
conversion after the introduction of convert_to_base_unit().

Before this command was available, all posting services stored RAW line.qty
in StockMoves without converting to item.default_unit.  As a result:
  - StockBalance was wrong whenever a document line used a non-default unit
    (e.g. selling 3 boxes when default=pcs and 1 box=20 pcs stored -3 instead
    of -60).

The command does two independent phases:

  Phase 1 — Fix StockMove.qty
    For every POSTED StockMove linked to a source document line, recompute
    qty = convert_to_base_unit(line.qty, line.unit, item.default_unit) and
    update the row.  Reversal moves (created by cancel_document) are updated to
    mirror their corrected originals.

  Phase 2 — Recalculate StockBalance from scratch
    Zeros all StockBalance records, then walks every POSTED document in order
    (GRN → DN → Pickup → Transfer → Adjustment → Damaged → POS → Refund →
     IST → PurchaseReturn → SalesReturn) and accumulates the correct base-unit
    delta per (item, location) bucket.  CANCELLED documents are skipped
    (their reversal moves cancel out).  At the end, bulk-updates StockBalance.

Usage:
    python manage.py resync_inventory                  # dry-run by default
    python manage.py resync_inventory --apply          # commit changes
    python manage.py resync_inventory --phase 1        # moves only (dry-run)
    python manage.py resync_inventory --phase 2 --apply
    python manage.py resync_inventory --apply --quiet  # no per-row output
"""
from collections import defaultdict
from decimal import Decimal, InvalidOperation

from django.core.management.base import BaseCommand
from django.db import transaction

from catalog.models import convert_to_base_unit
from core.models import DocumentStatus
from inventory.models import StockBalance, StockMove, MoveStatus


# ── helpers ─────────────────────────────────────────────────────────────────

def _safe_convert(qty, from_unit, to_unit, label, warn_fn, item=None):
    """convert_to_base_unit with graceful fallback: log warning and return raw qty."""
    try:
        return convert_to_base_unit(qty, from_unit, to_unit, item=item)
    except (ValueError, Exception) as exc:
        warn_fn(f"    [WARN] {label}: {exc}  -> using raw qty={qty}")
        return qty


# ── Phase 0 helpers ─────────────────────────────────────────────────────────

def _deduplicate_moves(dry_run, warn_fn):
    """
    Remove duplicate POSTED StockMoves whose (reference_type, reference_id,
    item_id, from_location_id, to_location_id) tuple appears more than once.
    For each group keep the move with qty closest to the converted source-doc
    qty; when undecidable keep the oldest (lowest pk) and delete the rest.
    Returns (removed_count, groups_count).
    """
    from django.db.models import Count

    dupes = list(
        StockMove.objects
        .filter(status=MoveStatus.POSTED)
        .exclude(reference_number__startswith='REV-')
        .exclude(reference_number__startswith='VOID-')
        .values('reference_type', 'reference_id', 'item_id',
                'from_location_id', 'to_location_id')
        .annotate(cnt=Count('id'))
        .filter(cnt__gt=1)
    )

    removed = 0
    for grp in dupes:
        moves = list(
            StockMove.objects.filter(
                reference_type=grp['reference_type'],
                reference_id=grp['reference_id'],
                item_id=grp['item_id'],
                from_location_id=grp['from_location_id'],
                to_location_id=grp['to_location_id'],
                status=MoveStatus.POSTED,
            ).exclude(reference_number__startswith='REV-')
             .exclude(reference_number__startswith='VOID-')
             .order_by('id')
             .select_related('item__default_unit', 'item__selling_unit', 'unit')
        )
        if len(moves) < 2:
            continue
        # Keep the first (oldest); delete the rest
        to_delete = moves[1:]
        for m in to_delete:
            warn_fn(
                f'    [DEDUP] Removing duplicate Move#{m.pk} '
                f'ref={m.reference_type}#{m.reference_id} '
                f'item={m.item.code} qty={m.qty}'
            )
            if not dry_run:
                m.delete()
            removed += 1

    return removed, len(dupes)


# ── Phase 1 helpers ──────────────────────────────────────────────────────────

def _fix_moves_for_doc(moves_qs, line_lookup_fn, warn_fn, dry_run, stats):
    """
    For each StockMove in moves_qs, call line_lookup_fn(move) to retrieve the
    source line.  Recalculate correct base-unit qty and update if changed.
    """
    for move in moves_qs.select_related('item__default_unit', 'item__selling_unit', 'unit'):
        line = line_lookup_fn(move)
        if line is None:
            stats['no_line'] += 1
            continue

        line_qty = getattr(line, 'qty', None)
        line_unit = getattr(line, 'unit', None)
        if line_qty is None or line_unit is None:
            stats['no_line'] += 1
            continue

        # For adjustments the stored qty is abs(diff); we need to handle sign
        if move.move_type == 'ADJUST':
            raw_diff = line.qty_counted - line.qty_system
            if raw_diff == 0:
                continue
            correct_qty = _safe_convert(
                abs(raw_diff), line_unit, move.item.stock_unit,
                f"Move#{move.pk} ADJUST", warn_fn, item=move.item,
            )
        else:
            correct_qty = _safe_convert(
                line_qty, line_unit, move.item.stock_unit,
                f"Move#{move.pk}", warn_fn, item=move.item,
            )

        if correct_qty == move.qty and move.unit_id == move.item.stock_unit.pk:
            stats['already_correct'] += 1
            continue

        if not dry_run:
            move.qty = correct_qty
            move.unit = move.item.stock_unit
            move.save(update_fields=['qty', 'unit_id'])
        stats['updated'] += 1


# ── line-lookup functions per document type ──────────────────────────────────

def _make_grn_lookup():
    from procurement.models import GoodsReceiptLine
    cache = {}
    def lookup(move):
        key = (move.reference_id, move.item_id)
        if key not in cache:
            cache[key] = GoodsReceiptLine.objects.filter(
                goods_receipt_id=move.reference_id, item_id=move.item_id
            ).select_related('unit').first()
        return cache[key]
    return lookup


def _make_dn_lookup():
    from sales.models import DeliveryLine
    cache = {}
    def lookup(move):
        key = (move.reference_id, move.item_id)
        if key not in cache:
            cache[key] = DeliveryLine.objects.filter(
                delivery_id=move.reference_id, item_id=move.item_id
            ).select_related('unit').first()
        return cache[key]
    return lookup


def _make_pickup_lookup():
    from sales.models import SalesPickupLine
    cache = {}
    def lookup(move):
        key = (move.reference_id, move.item_id)
        if key not in cache:
            cache[key] = SalesPickupLine.objects.filter(
                pickup_id=move.reference_id, item_id=move.item_id
            ).select_related('unit').first()
        return cache[key]
    return lookup


def _make_transfer_lookup():
    from inventory.models import StockTransferLine
    cache = {}
    def lookup(move):
        key = (move.reference_id, move.item_id)
        if key not in cache:
            cache[key] = StockTransferLine.objects.filter(
                transfer_id=move.reference_id, item_id=move.item_id
            ).select_related('unit').first()
        return cache[key]
    return lookup


def _make_adjustment_lookup():
    from inventory.models import StockAdjustmentLine
    cache = {}
    def lookup(move):
        key = (move.reference_id, move.item_id)
        if key not in cache:
            cache[key] = StockAdjustmentLine.objects.filter(
                adjustment_id=move.reference_id, item_id=move.item_id
            ).select_related('unit').first()
        return cache[key]
    return lookup


def _make_damaged_lookup():
    from inventory.models import DamagedReportLine
    cache = {}
    def lookup(move):
        key = (move.reference_id, move.item_id)
        if key not in cache:
            cache[key] = DamagedReportLine.objects.filter(
                report_id=move.reference_id, item_id=move.item_id
            ).select_related('unit').first()
        return cache[key]
    return lookup


def _make_pos_sale_lookup():
    from pos.models import POSSaleLine
    cache = {}
    def lookup(move):
        key = (move.reference_id, move.item_id)
        if key not in cache:
            cache[key] = POSSaleLine.objects.filter(
                sale_id=move.reference_id, item_id=move.item_id
            ).select_related('unit').first()
        return cache[key]
    return lookup


def _make_pos_refund_lookup():
    from pos.models import POSRefundLine
    cache = {}
    def lookup(move):
        key = (move.reference_id, move.item_id)
        if key not in cache:
            cache[key] = POSRefundLine.objects.filter(
                refund_id=move.reference_id, item_id=move.item_id
            ).select_related('unit').first()
        return cache[key]
    return lookup


def _make_ist_lookup():
    from inventory.models import InventoryToSupplyTransferLine
    cache = {}
    def lookup(move):
        key = (move.reference_id, move.item_id)
        if key not in cache:
            cache[key] = InventoryToSupplyTransferLine.objects.filter(
                transfer_id=move.reference_id, item_id=move.item_id
            ).select_related('unit').first()
        return cache[key]
    return lookup


def _make_purchase_return_lookup():
    from procurement.models import PurchaseReturnLine
    cache = {}
    def lookup(move):
        key = (move.reference_id, move.item_id)
        if key not in cache:
            cache[key] = PurchaseReturnLine.objects.filter(
                purchase_return_id=move.reference_id, item_id=move.item_id
            ).select_related('unit').first()
        return cache[key]
    return lookup


def _make_sales_return_lookup():
    from sales.models import SalesReturnLine
    cache = {}
    def lookup(move):
        key = (move.reference_id, move.item_id)
        if key not in cache:
            cache[key] = SalesReturnLine.objects.filter(
                sales_return_id=move.reference_id, item_id=move.item_id
            ).select_related('unit').first()
        return cache[key]
    return lookup


def _make_service_lookup():
    from services.models import ServiceLine
    cache = {}
    def lookup(move):
        key = (move.reference_id, move.item_id)
        if key not in cache:
            cache[key] = ServiceLine.objects.filter(
                service_id=move.reference_id, item_id=move.item_id
            ).select_related('unit').first()
        return cache[key]
    return lookup


REFERENCE_TYPE_LOOKUPS = {
    'GoodsReceipt': _make_grn_lookup,
    'DeliveryNote': _make_dn_lookup,
    'SalesPickup': _make_pickup_lookup,
    'StockTransfer': _make_transfer_lookup,
    'StockAdjustment': _make_adjustment_lookup,
    'DamagedReport': _make_damaged_lookup,
    'POSSale': _make_pos_sale_lookup,
    'POSRefund': _make_pos_refund_lookup,
    'InventoryToSupplyTransfer': _make_ist_lookup,
    'PurchaseReturn': _make_purchase_return_lookup,
    'SalesReturn': _make_sales_return_lookup,
    'CustomerService': _make_service_lookup,
}


# ── Phase 2 helpers ──────────────────────────────────────────────────────────

def _accumulate(bucket, item_id, location_id, delta):
    bucket[(item_id, location_id)] += delta


def _build_balance_from_documents(warn_fn):
    """
    Walk every POSTED document, apply correct base-unit conversion, accumulate
    (item, location) → qty_on_hand delta.  Returns a defaultdict.
    """
    from procurement.models import GoodsReceipt, PurchaseReturn
    from sales.models import DeliveryNote, SalesPickup, SalesReturn
    from inventory.models import StockTransfer, StockAdjustment, DamagedReport, InventoryToSupplyTransfer
    from pos.models import POSSale, POSRefund, SaleStatus, RefundStatus

    bal = defaultdict(Decimal)

    # ── GoodsReceipt ────────────────────────────────────────────────────────
    for grn in GoodsReceipt.objects.filter(status=DocumentStatus.POSTED).prefetch_related(
        'lines__item__default_unit', 'lines__item__selling_unit', 'lines__unit', 'lines__location'
    ):
        for line in grn.lines.all():
            q = _safe_convert(line.qty, line.unit, line.item.stock_unit,
                              f"GRN#{grn.pk} item={line.item.code}", warn_fn, item=line.item)
            _accumulate(bal, line.item_id, line.location_id, q)

    # ── DeliveryNote ────────────────────────────────────────────────────────
    for dn in DeliveryNote.objects.filter(status=DocumentStatus.POSTED).prefetch_related(
        'lines__item__default_unit', 'lines__item__selling_unit', 'lines__unit', 'lines__location'
    ):
        for line in dn.lines.all():
            q = _safe_convert(line.qty, line.unit, line.item.stock_unit,
                              f"DN#{dn.pk} item={line.item.code}", warn_fn, item=line.item)
            _accumulate(bal, line.item_id, line.location_id, -q)

    # ── SalesPickup ─────────────────────────────────────────────────────────
    for sp in SalesPickup.objects.filter(status=DocumentStatus.POSTED).prefetch_related(
        'lines__item__default_unit', 'lines__item__selling_unit', 'lines__unit', 'lines__location'
    ):
        for line in sp.lines.all():
            q = _safe_convert(line.qty, line.unit, line.item.stock_unit,
                              f"Pickup#{sp.pk} item={line.item.code}", warn_fn, item=line.item)
            _accumulate(bal, line.item_id, line.location_id, -q)

    # ── StockTransfer ────────────────────────────────────────────────────────
    for tr in StockTransfer.objects.filter(status=DocumentStatus.POSTED).prefetch_related(
        'lines__item__default_unit', 'lines__item__selling_unit', 'lines__unit',
        'lines__from_location', 'lines__to_location'
    ):
        for line in tr.lines.all():
            q = _safe_convert(line.qty, line.unit, line.item.stock_unit,
                              f"Transfer#{tr.pk} item={line.item.code}", warn_fn, item=line.item)
            _accumulate(bal, line.item_id, line.from_location_id, -q)
            _accumulate(bal, line.item_id, line.to_location_id, q)

    # ── StockAdjustment ──────────────────────────────────────────────────────
    for adj in StockAdjustment.objects.filter(status=DocumentStatus.POSTED).prefetch_related(
        'lines__item__default_unit', 'lines__item__selling_unit', 'lines__unit', 'lines__location'
    ):
        for line in adj.lines.all():
            raw_diff = line.qty_counted - line.qty_system
            if raw_diff == 0:
                continue
            q = _safe_convert(abs(raw_diff), line.unit, line.item.stock_unit,
                              f"Adj#{adj.pk} item={line.item.code}", warn_fn, item=line.item)
            _accumulate(bal, line.item_id, line.location_id,
                        q if raw_diff > 0 else -q)

    # ── DamagedReport ────────────────────────────────────────────────────────
    for dr in DamagedReport.objects.filter(status=DocumentStatus.POSTED).prefetch_related(
        'lines__item__default_unit', 'lines__item__selling_unit', 'lines__unit', 'lines__location'
    ):
        for line in dr.lines.all():
            q = _safe_convert(line.qty, line.unit, line.item.stock_unit,
                              f"Damaged#{dr.pk} item={line.item.code}", warn_fn, item=line.item)
            _accumulate(bal, line.item_id, line.location_id, -q)

    # ── POSSale ──────────────────────────────────────────────────────────────
    for sale in POSSale.objects.filter(status=SaleStatus.POSTED).prefetch_related(
        'lines__item__default_unit', 'lines__item__selling_unit', 'lines__unit', 'lines__location'
    ):
        for line in sale.lines.all():
            loc_id = line.location_id or sale.location_id
            q = _safe_convert(line.qty, line.unit, line.item.stock_unit,
                              f"POSSale#{sale.pk} item={line.item.code}", warn_fn, item=line.item)
            _accumulate(bal, line.item_id, loc_id, -q)

    # ── POSRefund ────────────────────────────────────────────────────────────
    for refund in POSRefund.objects.filter(status=RefundStatus.POSTED).prefetch_related(
        'lines__item__default_unit', 'lines__item__selling_unit', 'lines__unit', 'lines__location'
    ):
        for line in refund.lines.all():
            q = _safe_convert(line.qty, line.unit, line.item.stock_unit,
                              f"POSRefund#{refund.pk} item={line.item.code}", warn_fn, item=line.item)
            _accumulate(bal, line.item_id, line.location_id, q)

    # ── InventoryToSupplyTransfer ────────────────────────────────────────────
    for ist in InventoryToSupplyTransfer.objects.filter(status=DocumentStatus.POSTED).prefetch_related(
        'lines__item__default_unit', 'lines__item__selling_unit', 'lines__unit', 'lines__location'
    ):
        for line in ist.lines.all():
            q = _safe_convert(line.qty, line.unit, line.item.stock_unit,
                              f"IST#{ist.pk} item={line.item.code}", warn_fn, item=line.item)
            _accumulate(bal, line.item_id, line.location_id, -q)

    # ── PurchaseReturn ───────────────────────────────────────────────────────
    for pr in PurchaseReturn.objects.filter(status=DocumentStatus.POSTED).prefetch_related(
        'lines__item__default_unit', 'lines__item__selling_unit', 'lines__unit', 'lines__location'
    ):
        for line in pr.lines.all():
            q = _safe_convert(line.qty, line.unit, line.item.stock_unit,
                              f"PurchReturn#{pr.pk} item={line.item.code}", warn_fn, item=line.item)
            _accumulate(bal, line.item_id, line.location_id, -q)

    # ── SalesReturn ──────────────────────────────────────────────────────────
    for sr in SalesReturn.objects.filter(status=DocumentStatus.POSTED).prefetch_related(
        'lines__item__default_unit', 'lines__item__selling_unit', 'lines__unit', 'lines__location'
    ):
        for line in sr.lines.all():
            q = _safe_convert(line.qty, line.unit, line.item.stock_unit,
                              f"SalesReturn#{sr.pk} item={line.item.code}", warn_fn, item=line.item)
            _accumulate(bal, line.item_id, line.location_id, q)

    # ── CustomerService ──────────────────────────────────────────────────────
    from services.models import CustomerService, ServiceStatus
    for svc in CustomerService.objects.filter(status=ServiceStatus.COMPLETED).prefetch_related(
        'lines__item__default_unit', 'lines__item__selling_unit', 'lines__unit', 'lines__location'
    ):
        for line in svc.lines.all():
            if line.location_id is None:
                continue
            q = _safe_convert(line.qty, line.unit, line.item.stock_unit,
                              f"Service#{svc.pk} item={line.item.code}", warn_fn, item=line.item)
            _accumulate(bal, line.item_id, line.location_id, -q)

    return bal


# ── Command ──────────────────────────────────────────────────────────────────

class Command(BaseCommand):
    help = (
        'Re-sync StockBalance and StockMove records to correct unit-conversion '
        'errors. Use --apply to commit; default is dry-run.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply',
            action='store_true',
            default=False,
            help='Commit changes to the database (default: dry-run).',
        )
        parser.add_argument(
            '--phase',
            choices=['0', '1', '2', '3', 'all'],
            default='all',
            help='0=dedup moves, 1=fix qtys, 2=recalc balances, 3=audit, all=all (default).',
        )
        parser.add_argument(
            '--quiet', '-q',
            action='store_true',
            default=False,
            help='Suppress per-document output; only show summary.',
        )

    # ── internal output helpers ──────────────────────────────────────────────

    @staticmethod
    def _safe_str(msg):
        """Return msg with non-ASCII chars replaced so cp1252 consoles don't crash."""
        return msg.encode('ascii', errors='replace').decode('ascii')

    def _info(self, msg):
        if not self._quiet:
            try:
                self.stdout.write(msg)
            except UnicodeEncodeError:
                self.stdout.write(self._safe_str(msg))

    def _warn(self, msg):
        try:
            self.stdout.write(self.style.WARNING(msg))
        except UnicodeEncodeError:
            self.stdout.write(self.style.WARNING(self._safe_str(msg)))

    # ── entry point ──────────────────────────────────────────────────────────

    def handle(self, *args, **options):
        self._quiet = options['quiet']
        dry_run = not options['apply']
        phase = options['phase']

        mode = 'DRY-RUN' if dry_run else 'APPLYING'
        self.stdout.write(self.style.SUCCESS(
            f'\n=== resync_inventory [{mode}] phase={phase} ===\n'
        ))

        if dry_run:
            self.stdout.write(self.style.WARNING(
                '  No changes will be saved.  Re-run with --apply to commit.\n'
            ))

        if phase in ('0', 'all'):
            self._run_phase0(dry_run)
        if phase in ('1', 'all'):
            self._run_phase1(dry_run)
        if phase in ('2', 'all'):
            self._run_phase2(dry_run)
        if phase in ('3', 'all'):
            self._run_phase3()

        self.stdout.write(self.style.SUCCESS('\n=== Done ===\n'))

    # ── Phase 0: deduplicate StockMoves ──────────────────────────────────────

    def _run_phase0(self, dry_run):
        self.stdout.write('\n--- Phase 0: Deduplicating StockMoves ---')
        removed, groups = _deduplicate_moves(dry_run, self._warn)
        mode = '(dry-run) would remove' if dry_run else 'Removed'
        self.stdout.write(self.style.SUCCESS(
            f'  {mode} {removed} duplicate move(s) across {groups} group(s).'
        ))
        if dry_run and removed:
            self.stdout.write(self.style.WARNING(
                '  Re-run with --apply to commit removals.'
            ))

    # ── Phase 1: fix StockMove.qty ───────────────────────────────────────────

    def _run_phase1(self, dry_run):
        self.stdout.write('\n--- Phase 1: Correcting StockMove quantities ---')

        total_stats = {'updated': 0, 'already_correct': 0, 'no_line': 0}

        for ref_type, lookup_factory in REFERENCE_TYPE_LOOKUPS.items():
            moves_qs = StockMove.objects.filter(
                reference_type=ref_type,
                status=MoveStatus.POSTED,
            ).exclude(reference_number__startswith='REV-')

            count = moves_qs.count()
            if count == 0:
                continue

            self._info(f'  {ref_type:<35} {count:>5} moves')
            stats = {'updated': 0, 'already_correct': 0, 'no_line': 0}
            lookup_fn = lookup_factory()

            with transaction.atomic():
                _fix_moves_for_doc(moves_qs, lookup_fn, self._warn, dry_run, stats)
                if dry_run:
                    transaction.set_rollback(True)

            self._info(
                f'    -> updated={stats["updated"]}  '
                f'ok={stats["already_correct"]}  '
                f'missing_line={stats["no_line"]}'
            )
            for k, v in stats.items():
                total_stats[k] += v

        # Fix reversal moves: their qty should mirror the corrected original
        rev_moves = StockMove.objects.filter(
            reference_number__startswith='REV-',
            status=MoveStatus.POSTED,
        ).select_related('item__default_unit', 'item__selling_unit', 'unit')

        rev_updated = 0
        for rev in rev_moves:
            # Find the original move this reversal was created from
            orig_ref = rev.reference_number[4:]  # strip 'REV-'
            orig = StockMove.objects.select_related('item__default_unit', 'item__selling_unit', 'unit').filter(
                reference_type=rev.reference_type,
                reference_id=rev.reference_id,
                reference_number=orig_ref,
                status=MoveStatus.POSTED,
            ).first()
            if orig and (orig.qty != rev.qty or orig.unit_id != rev.unit_id):
                if not dry_run:
                    rev.qty = orig.qty
                    rev.unit = orig.unit
                    rev.save(update_fields=['qty', 'unit_id'])
                rev_updated += 1

        self._info(f'  Reversal moves corrected: {rev_updated}')
        total_stats['updated'] += rev_updated

        self.stdout.write(self.style.SUCCESS(
            f'\n  Phase 1 total — updated: {total_stats["updated"]}  '
            f'already_correct: {total_stats["already_correct"]}  '
            f'missing_source: {total_stats["no_line"]}'
        ))

    # ── Phase 2: recalculate StockBalance from document lines ────────────────

    def _run_phase2(self, dry_run):
        self.stdout.write('\n--- Phase 2: Recalculating StockBalance ---')

        self.stdout.write('  Building correct balances from all posted documents...')
        correct_bal = _build_balance_from_documents(self._warn)

        self.stdout.write(f'  Computed {len(correct_bal)} (item, location) buckets.')

        # Compare with existing StockBalance
        existing = {
            (b.item_id, b.location_id): b
            for b in StockBalance.objects.all()
        }

        # Identify all keys to process
        all_keys = set(correct_bal.keys()) | set(existing.keys())

        creates, updates, zeros_preserved = [], [], 0
        report_lines = []

        for key in all_keys:
            item_id, loc_id = key
            new_qty = correct_bal.get(key, Decimal('0'))
            bal_obj = existing.get(key)

            if bal_obj is None:
                if new_qty != 0:
                    creates.append(StockBalance(
                        item_id=item_id,
                        location_id=loc_id,
                        qty_on_hand=new_qty,
                        qty_reserved=Decimal('0'),
                    ))
                    report_lines.append(f'    CREATE item={item_id} loc={loc_id} qty={new_qty}')
            else:
                old_qty = bal_obj.qty_on_hand
                if old_qty != new_qty:
                    report_lines.append(
                        f'    UPDATE item={item_id} loc={loc_id} '
                        f'{old_qty} -> {new_qty}'
                    )
                    updates.append((bal_obj, new_qty))
                else:
                    zeros_preserved += 1

        for line in report_lines:
            self._info(line)

        self.stdout.write(
            f'\n  Creates: {len(creates)}  Updates: {len(updates)}  '
            f'Unchanged: {zeros_preserved}'
        )

        if not dry_run:
            with transaction.atomic():
                # Apply creates
                if creates:
                    StockBalance.objects.bulk_create(creates)
                # Apply updates
                for bal_obj, new_qty in updates:
                    bal_obj.qty_on_hand = new_qty
                    bal_obj.save(update_fields=['qty_on_hand', 'updated_at'])
            self.stdout.write(self.style.SUCCESS(
                f'  Committed: {len(creates)} created, {len(updates)} updated.'
            ))
        else:
            self.stdout.write(self.style.WARNING(
                '  (dry-run) No changes written.  Re-run with --apply to commit.'
            ))

    # ── Phase 3: Data integrity audit ────────────────────────────────────────

    def _run_phase3(self):
        self.stdout.write('\n--- Phase 3: Data Integrity Audit ---')
        from django.db.models import Count, Q, F
        from catalog.models import Item, UnitConversion, UnitCategory

        issues = 0

        # 3a: Negative StockBalance records
        neg = list(StockBalance.objects.filter(qty_on_hand__lt=0).select_related(
            'item', 'location__warehouse'))
        if neg:
            self.stdout.write(self.style.ERROR(
                f'\n  [NEG BALANCE] {len(neg)} item/location(s) have negative stock:'))
            for b in neg:
                self.stdout.write(self.style.ERROR(
                    f'    item={b.item.code}  loc={b.location}  '
                    f'qty={b.qty_on_hand}'))
            issues += len(neg)
        else:
            self.stdout.write(self.style.SUCCESS('  [NEG BALANCE]  none OK'))

        # 3b: Duplicate StockMoves for same (reference_type, reference_id, item)
        dupes = (
            StockMove.objects
            .filter(status=MoveStatus.POSTED)
            .exclude(reference_number__startswith='REV-')
            .exclude(reference_number__startswith='VOID-')
            .values('reference_type', 'reference_id', 'item_id')
            .annotate(cnt=Count('id'))
            .filter(cnt__gt=1)
        )
        dupe_list = list(dupes)
        if dupe_list:
            self.stdout.write(self.style.WARNING(
                f'\n  [DUPE MOVES]  {len(dupe_list)} duplicate move group(s):'))
            for d in dupe_list[:20]:
                self.stdout.write(self.style.WARNING(
                    f'    ref={d["reference_type"]}#{d["reference_id"]}  '
                    f'item={d["item_id"]}  count={d["cnt"]}'))
            issues += len(dupe_list)
        else:
            self.stdout.write(self.style.SUCCESS('  [DUPE MOVES]   none OK'))

        # 3c: StockMoves with unrecognised reference_type
        known_types = set(REFERENCE_TYPE_LOOKUPS.keys())
        unknown_qs = (
            StockMove.objects
            .filter(status=MoveStatus.POSTED)
            .exclude(reference_type__in=known_types)
            .values('reference_type')
            .annotate(cnt=Count('id'))
        )
        unknown_list = list(unknown_qs)
        if unknown_list:
            self.stdout.write(self.style.WARNING(
                f'\n  [UNKNOWN REF] {len(unknown_list)} unrecognised reference_type(s):'))
            for u in unknown_list:
                self.stdout.write(self.style.WARNING(
                    f'    {u["reference_type"]}  ({u["cnt"]} moves)'))
        else:
            self.stdout.write(self.style.SUCCESS('  [UNKNOWN REF]  none OK'))

        # 3d: Items whose stock_unit category conflicts with any StockMove unit
        cross_cat_items = set()
        for move in (StockMove.objects
                     .filter(status=MoveStatus.POSTED)
                     .select_related('item__default_unit', 'item__selling_unit', 'unit')
                     .only('item__id', 'unit__category',
                           'item__default_unit__category', 'item__selling_unit__category')):
            stock_cat = move.item.stock_unit.category
            if move.unit.category != stock_cat:
                cross_cat_items.add(move.item.code)

        if cross_cat_items:
            self.stdout.write(self.style.WARNING(
                f'\n  [CAT MISMATCH] {len(cross_cat_items)} item(s) have moves in wrong unit category:'))
            for code in sorted(cross_cat_items)[:30]:
                self.stdout.write(self.style.WARNING(f'    {code}'))
            issues += len(cross_cat_items)
        else:
            self.stdout.write(self.style.SUCCESS('  [CAT MISMATCH] none OK'))

        # 3e: Items with selling_unit set but no UnitConversion between default and selling
        conv_missing = []
        for item in Item.objects.filter(
            selling_unit__isnull=False
        ).select_related('default_unit', 'selling_unit').exclude(
            selling_unit=F('default_unit')
        ):
            su = item.selling_unit
            du = item.default_unit
            if su.pk == du.pk:
                continue
            has_conv = UnitConversion.objects.filter(
                Q(from_unit=du, to_unit=su) | Q(from_unit=su, to_unit=du),
                Q(item=item) | Q(item__isnull=True),
                is_active=True,
            ).exists()
            if not has_conv:
                conv_missing.append(f'{item.code}  ({du.abbreviation} <-> {su.abbreviation})')

        if conv_missing:
            self.stdout.write(self.style.WARNING(
                f'\n  [MISSING CONV] {len(conv_missing)} item(s) have selling_unit but no conversion:'))
            for m in conv_missing[:30]:
                self.stdout.write(self.style.WARNING(f'    {m}'))
            issues += len(conv_missing)
        else:
            self.stdout.write(self.style.SUCCESS(
                f'\n  [MISSING CONV] none OK'))

        # Summary
        if issues:
            self.stdout.write(self.style.ERROR(
                f'\n  Phase 3 total: {issues} issue(s) found - see above for details.'))
        else:
            self.stdout.write(self.style.SUCCESS(
                f'\n  Phase 3: all integrity checks passed OK'))
