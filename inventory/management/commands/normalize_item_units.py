"""
Management command: normalize_item_units
==========================================
One-time data-migration tool for items that were consolidated to a single
default/selling unit (see backfill_item_selling_units) but still have
historical document lines and StockMoves recorded in a different, no-longer-
used unit.  Unlike a UnitConversion bridge record (which resync_inventory
would use forever), this REWRITES those old rows in place: qty *= factor,
unit_id -> the item's current default unit.  After running, no conversion
is ever needed for that (item, old-unit) pair again.

Scope is a hardcoded table of (item_code, from_unit_abbr, factor) pairs,
verified against real PO<->GRN quantity pairs (or supplied by the business)
during the missing_conversions_detailed_report.txt investigation.  This is
deliberately NOT a generic "fix everything" tool — guessing a wrong factor
silently corrupts real stock qty/cost history, so only pre-confirmed pairs
are listed here.

Usage:
    python manage.py normalize_item_units --item TOO-Tox-5 --dry-run
    python manage.py normalize_item_units --item TOO-Tox-5
    python manage.py normalize_item_units --all --dry-run
    python manage.py normalize_item_units --all
"""
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction


# (item_code, from_unit_abbr, to_unit_abbr, factor)
# factor: qty_in_from_unit * factor = qty_in_to_unit
CONFIRMED_FACTORS = [
    ('TOO-Tox-5', 'pcs', 'pks', Decimal('1')),
    ('ACC-ALCOMESH #36-HA', 'pcs', 'ft', Decimal('14')),
    ('ACC-ALCOMESH #36-PCW', 'pcs', 'ft', Decimal('14')),
    ('ACC-ExpandWire#36-HA', 'ft', 'm', Decimal('0.3048')),
    ('ACC-RedMo-S', 'roll', 'm', Decimal('150')),
    ('ACC-S-48-HA-SKY', 'roll', 'm', Decimal('30')),
    ('ACC-ScreenMesh-#36-HA', 'ft', 'm', Decimal('0.3048')),
    ('ACC-ScreenMesh-#36-HA', 'roll', 'm', Decimal('100')),
    ('ACC-ScreenMesh-#48-A', 'ft', 'm', Decimal('0.3048')),
]

# (label, model_path, qty_field, fk_to_item='item')
LINE_TABLES = [
    ('GoodsReceiptLine', 'procurement.models.GoodsReceiptLine', 'qty'),
    ('PurchaseOrderLine', 'procurement.models.PurchaseOrderLine', 'qty_ordered'),
    ('PurchaseReturnLine', 'procurement.models.PurchaseReturnLine', 'qty'),
    ('DeliveryLine', 'sales.models.DeliveryLine', 'qty'),
    ('SalesPickupLine', 'sales.models.SalesPickupLine', 'qty'),
    ('SalesReturnLine', 'sales.models.SalesReturnLine', 'qty'),
    ('SalesOrderLine', 'sales.models.SalesOrderLine', 'qty_ordered'),
    ('ServiceLine', 'services.models.ServiceLine', 'qty'),
    ('StockMove', 'inventory.models.StockMove', 'qty'),
]


def _import_model(path):
    module_path, name = path.rsplit('.', 1)
    import importlib
    module = importlib.import_module(module_path)
    return getattr(module, name)


class Command(BaseCommand):
    help = (
        'Rewrite historical document lines/StockMoves for pre-confirmed items '
        'from an old unit to the item\'s current single default unit '
        '(qty *= factor, unit -> default). Run resync_inventory afterwards.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--item', action='append', default=[],
                             help='Item code to process (repeatable). Default: all confirmed items.')
        parser.add_argument('--all', action='store_true', help='Process every confirmed item.')
        parser.add_argument('--dry-run', action='store_true', help='Preview without saving.')

    def handle(self, *args, **options):
        from catalog.models import Unit, Item

        dry_run = options['dry_run']
        requested = set(options['item'])
        if not requested and not options['all']:
            raise CommandError('Specify --item CODE (repeatable) or --all.')

        pairs = [p for p in CONFIRMED_FACTORS if not requested or p[0] in requested]
        if not pairs:
            raise CommandError('No matching confirmed item codes found.')

        mode = 'DRY-RUN' if dry_run else 'APPLYING'
        self.stdout.write(self.style.SUCCESS(f'\n=== normalize_item_units [{mode}] ===\n'))

        unit_cache = {}

        def get_unit(abbr):
            if abbr not in unit_cache:
                unit_cache[abbr] = Unit.objects.get(abbreviation=abbr)
            return unit_cache[abbr]

        grand_total = 0

        with transaction.atomic():
            for item_code, from_abbr, to_abbr, factor in pairs:
                try:
                    item = Item.all_objects.get(code=item_code)
                except Item.DoesNotExist:
                    self.stdout.write(self.style.ERROR(f'  Item {item_code} not found — skipping.'))
                    continue

                from_unit = get_unit(from_abbr)
                to_unit = get_unit(to_abbr)

                if item.default_unit_id != to_unit.pk:
                    self.stdout.write(self.style.WARNING(
                        f'  {item_code}: default_unit is "{item.default_unit.abbreviation}", '
                        f'not "{to_abbr}" — skipping (config out of date?).'
                    ))
                    continue

                self.stdout.write(f'\n  --- {item_code}: {from_abbr} -> {to_abbr}  (factor={factor}) ---')
                item_total = 0

                for label, model_path, qty_field in LINE_TABLES:
                    Model = _import_model(model_path)
                    manager = getattr(Model, 'all_objects', Model.objects)
                    qs = manager.filter(item_id=item.pk, unit_id=from_unit.pk)
                    count = qs.count()
                    if count == 0:
                        continue

                    total_qty = sum((getattr(r, qty_field) or Decimal('0')) for r in qs)
                    self.stdout.write(
                        f'    {label:20s} {count:4d} row(s), total {qty_field}={total_qty} {from_abbr} '
                        f'-> {total_qty * factor} {to_abbr}'
                    )
                    item_total += count

                    if not dry_run:
                        for row in qs:
                            old_qty = getattr(row, qty_field) or Decimal('0')
                            setattr(row, qty_field, old_qty * factor)
                            row.unit_id = to_unit.pk
                            row.save(update_fields=[qty_field, 'unit_id'])

                self.stdout.write(f'    -> {item_total} row(s) touched for {item_code}')
                grand_total += item_total

            if dry_run:
                transaction.set_rollback(True)

        self.stdout.write('')
        if dry_run:
            self.stdout.write(self.style.WARNING(
                f'DRY-RUN complete: {grand_total} row(s) would be updated. Re-run without --dry-run to commit.'
            ))
        else:
            self.stdout.write(self.style.SUCCESS(f'Done! Updated {grand_total} row(s).'))
            self.stdout.write(self.style.SUCCESS(
                'Run "python manage.py resync_inventory" next to rebuild StockMoves/StockBalances.'
            ))
