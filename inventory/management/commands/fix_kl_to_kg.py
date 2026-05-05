"""
Management command: fix_kl_to_kg
=================================
Fixes the mis-selected "kl" unit to "kg" (Kilogram) across all affected
records: GoodsReceiptLine, DeliveryLine, SalesPickupLine, and StockMove.

Only affects item ACC-CG-b where "kl" was mistakenly used instead of "kg".

Usage:
    python manage.py fix_kl_to_kg              # apply fix
    python manage.py fix_kl_to_kg --dry-run    # preview without saving
"""
from django.core.management.base import BaseCommand
from django.db import transaction


class Command(BaseCommand):
    help = 'Fix mis-selected "kl" unit to "kg" on ACC-CG-b across GRNs, Deliveries, Pickups, and StockMoves.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Preview changes without writing to the database.',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        mode = 'DRY-RUN' if dry_run else 'APPLYING'
        self.stdout.write(self.style.SUCCESS(f'\n=== fix_kl_to_kg [{mode}] ===\n'))

        from catalog.models import Unit, Item
        from procurement.models import GoodsReceiptLine
        from sales.models import DeliveryLine, SalesPickupLine
        from inventory.models import StockMove

        # Look up the units
        try:
            kl_unit = Unit.objects.get(abbreviation='kl')
        except Unit.DoesNotExist:
            self.stdout.write(self.style.ERROR('  Unit with abbreviation "kl" not found. Nothing to fix.'))
            return

        try:
            kg_unit = Unit.objects.get(abbreviation='kg')
        except Unit.DoesNotExist:
            self.stdout.write(self.style.ERROR('  Unit with abbreviation "kg" not found. Cannot proceed.'))
            return

        self.stdout.write(f'  Found: kl = Unit#{kl_unit.pk} ("{kl_unit.name}")')
        self.stdout.write(f'  Found: kg = Unit#{kg_unit.pk} ("{kg_unit.name}")')
        self.stdout.write('')

        total_fixed = 0

        with transaction.atomic():
            # 1. Fix GoodsReceiptLine records
            grn_lines = GoodsReceiptLine.objects.filter(unit=kl_unit)
            grn_count = grn_lines.count()
            if grn_count:
                self.stdout.write(f'  GoodsReceiptLine: {grn_count} record(s) with unit=kl')
                for line in grn_lines.select_related('item', 'goods_receipt'):
                    self.stdout.write(
                        f'    → GRN#{line.goods_receipt_id} item={line.item.code} '
                        f'qty={line.qty} kl → kg'
                    )
                if not dry_run:
                    grn_lines.update(unit=kg_unit)
                total_fixed += grn_count
            else:
                self.stdout.write('  GoodsReceiptLine: 0 records with unit=kl ✓')

            # 2. Fix DeliveryLine records
            dn_lines = DeliveryLine.objects.filter(unit=kl_unit)
            dn_count = dn_lines.count()
            if dn_count:
                self.stdout.write(f'  DeliveryLine: {dn_count} record(s) with unit=kl')
                for line in dn_lines.select_related('item', 'delivery'):
                    self.stdout.write(
                        f'    → DN#{line.delivery_id} item={line.item.code} '
                        f'qty={line.qty} kl → kg'
                    )
                if not dry_run:
                    dn_lines.update(unit=kg_unit)
                total_fixed += dn_count
            else:
                self.stdout.write('  DeliveryLine: 0 records with unit=kl ✓')

            # 3. Fix SalesPickupLine records
            pickup_lines = SalesPickupLine.objects.filter(unit=kl_unit)
            pickup_count = pickup_lines.count()
            if pickup_count:
                self.stdout.write(f'  SalesPickupLine: {pickup_count} record(s) with unit=kl')
                for line in pickup_lines.select_related('item', 'pickup'):
                    self.stdout.write(
                        f'    → Pickup#{line.pickup_id} item={line.item.code} '
                        f'qty={line.qty} kl → kg'
                    )
                if not dry_run:
                    pickup_lines.update(unit=kg_unit)
                total_fixed += pickup_count
            else:
                self.stdout.write('  SalesPickupLine: 0 records with unit=kl ✓')

            # 4. Fix StockMove records
            moves = StockMove.objects.filter(unit=kl_unit)
            move_count = moves.count()
            if move_count:
                self.stdout.write(f'  StockMove: {move_count} record(s) with unit=kl')
                for move in moves.select_related('item'):
                    self.stdout.write(
                        f'    → Move#{move.pk} item={move.item.code} '
                        f'qty={move.qty} ref={move.reference_type}#{move.reference_id} kl → kg'
                    )
                if not dry_run:
                    moves.update(unit=kg_unit)
                total_fixed += move_count
            else:
                self.stdout.write('  StockMove: 0 records with unit=kl ✓')

            # 5. Check if any Item has default_unit or selling_unit set to kl
            items_default = Item.objects.filter(default_unit=kl_unit)
            items_selling = Item.objects.filter(selling_unit=kl_unit)
            item_default_count = items_default.count()
            item_selling_count = items_selling.count()

            if item_default_count:
                self.stdout.write(f'  Item.default_unit: {item_default_count} item(s) with unit=kl')
                for item in items_default:
                    self.stdout.write(f'    → {item.code} default_unit kl → kg')
                if not dry_run:
                    items_default.update(default_unit=kg_unit)
                total_fixed += item_default_count
            else:
                self.stdout.write('  Item.default_unit: 0 items with unit=kl ✓')

            if item_selling_count:
                self.stdout.write(f'  Item.selling_unit: {item_selling_count} item(s) with unit=kl')
                for item in items_selling:
                    self.stdout.write(f'    → {item.code} selling_unit kl → kg')
                if not dry_run:
                    items_selling.update(selling_unit=kg_unit)
                total_fixed += item_selling_count
            else:
                self.stdout.write('  Item.selling_unit: 0 items with unit=kl ✓')

            if dry_run:
                transaction.set_rollback(True)

        self.stdout.write('')
        if dry_run:
            self.stdout.write(self.style.WARNING(
                f'  DRY-RUN complete: {total_fixed} record(s) would be updated. '
                f'Re-run without --dry-run to commit.'
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                f'  Done! Fixed {total_fixed} record(s): kl → kg.'
            ))
            self.stdout.write(self.style.SUCCESS(
                '  Run "resync_inventory" next to rebuild StockBalances.'
            ))
