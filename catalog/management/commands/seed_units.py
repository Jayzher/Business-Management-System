"""
Management command: seed_units
Idempotently creates or updates the standard units of measure.
Run with:  python manage.py seed_units
"""
from django.core.management.base import BaseCommand
from catalog.models import Unit, UnitCategory


UNITS = [
    # --- Quantity ---
    ('Piece',        'pcs',  UnitCategory.QUANTITY),
    ('Unit',         'unit', UnitCategory.QUANTITY),
    ('Set',          'set',  UnitCategory.QUANTITY),
    ('Pair',         'pr',   UnitCategory.QUANTITY),
    ('Dozen',        'doz',  UnitCategory.QUANTITY),
    ('Gross',        'GRS',  UnitCategory.QUANTITY),
    ('Pack',         'pks',  UnitCategory.QUANTITY),
    ('Box',          'bx',   UnitCategory.QUANTITY),
    ('Carton',       'ctn',  UnitCategory.QUANTITY),
    ('Bundle',       'bdl',  UnitCategory.QUANTITY),
    ('Sack',         'sk',   UnitCategory.QUANTITY),
    ('Lot',          'lot',  UnitCategory.QUANTITY),
    # --- Length ---
    ('Millimeter',   'mm',   UnitCategory.LENGTH),
    ('Centimeter',   'cm',   UnitCategory.LENGTH),
    ('Meter',        'm',    UnitCategory.LENGTH),
    ('Kilometer',    'km',   UnitCategory.LENGTH),
    ('Inch',         'in',   UnitCategory.LENGTH),
    ('Foot',         'ft',   UnitCategory.LENGTH),
    ('Yard',         'yd',   UnitCategory.LENGTH),
    ('Mile',         'mi',   UnitCategory.LENGTH),
    # --- Mass ---
    ('Milligram',    'mg',   UnitCategory.MASS),
    ('Gram',         'g',    UnitCategory.MASS),
    ('Kilogram',     'kg',   UnitCategory.MASS),
    ('Metric Ton',   't',    UnitCategory.MASS),
    ('Pound',        'lb',   UnitCategory.MASS),
    ('Ounce',        'oz',   UnitCategory.MASS),
    # --- Volume ---
    ('Milliliter',   'mL',   UnitCategory.VOLUME),
    ('Liter',        'L',    UnitCategory.VOLUME),
    ('Kiloliter',    'kL',   UnitCategory.VOLUME),
    ('Cubic meter',  'm3',   UnitCategory.VOLUME),
    ('Gallon',       'gal',  UnitCategory.VOLUME),
    ('Quart',        'qt',   UnitCategory.VOLUME),
    ('Pint',         'pt',   UnitCategory.VOLUME),
    # --- Area ---
    ('Square meter',     'm2',   UnitCategory.AREA),
    ('Square kilometer', 'km2',  UnitCategory.AREA),
    ('Square foot',      'ft2',  UnitCategory.AREA),
    ('Square inch',      'in2',  UnitCategory.AREA),
    ('Hectare',          'ha',   UnitCategory.AREA),
    ('Acre',             'acre', UnitCategory.AREA),
    # --- Material ---
    ('Sheet',   'sht',  UnitCategory.MATERIAL),
    ('Roll',    'roll', UnitCategory.MATERIAL),
    ('Panel',   'pnl',  UnitCategory.MATERIAL),
    ('Slab',    'slab', UnitCategory.MATERIAL),
    ('Bar',     'bar',  UnitCategory.MATERIAL),
    ('Rod',     'rod',  UnitCategory.MATERIAL),
    ('Pipe',    'pipe', UnitCategory.MATERIAL),
    # --- Logistics ---
    ('Pallet',    'plt',   UnitCategory.LOGISTICS),
    ('Container', 'ctr',   UnitCategory.LOGISTICS),
    ('Drum',      'drm',   UnitCategory.LOGISTICS),
    ('Tank',      'tank',  UnitCategory.LOGISTICS),
    ('Tray',      'tray',  UnitCategory.LOGISTICS),
]

COMMON_CONVERSIONS = [
    # quantity conversions that are easy multipliers
    ('doz', 'pcs', '12'),
    ('GRS', 'pcs', '144'),
    ('pks', 'pcs', '10'),
    ('bx', 'pcs', '20'),
    # length chain (simple multiples)
    ('km', 'm', '1000'),
    ('m', 'cm', '100'),
    ('cm', 'mm', '10'),
    ('ft', 'in', '12'),
    # mass conversions
    ('kg', 'g', '1000'),
    ('g', 'mg', '1000'),
    ('lb', 'oz', '16'),
    # volume conversions
    ('L', 'mL', '1000'),
    ('kL', 'L', '1000'),
    ('gal', 'qt', '4'),
    # material conversions (common roll/meter)
    ('roll', 'm', '50'),
    ('sht', 'm2', '2'),
]


class Command(BaseCommand):
    help = 'Seed the standard units of measure with categories.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--update-existing',
            action='store_true',
            help='Update category on existing units even if the name already exists.',
        )

    def handle(self, *args, **options):
        update_existing = options['update_existing']
        created = updated = skipped = 0

        for name, abbr, cat in UNITS:
            # Use the base (unfiltered) manager so soft-deleted rows are matched
            # and reactivated rather than causing a UNIQUE constraint error.
            qs = Unit.all_objects if hasattr(Unit, 'all_objects') else Unit._default_manager
            try:
                obj = qs.get(abbreviation=abbr)
                was_created = False
            except Unit.DoesNotExist:
                obj = None
                was_created = True

            if was_created:
                Unit._default_manager.create(
                    name=name, abbreviation=abbr, category=cat, is_active=True)
                created += 1
                self.stdout.write(self.style.SUCCESS(f'  Created  {abbr:<8} {name} [{cat}]'))
            else:
                changed = False
                if not obj.is_active:
                    obj.is_active = True
                    changed = True
                if update_existing and obj.category != cat:
                    self.stdout.write(self.style.WARNING(
                        f'  Updated  {abbr:<8} {name}: {obj.category} → {cat}'))
                    obj.category = cat
                    obj.name = name
                    changed = True
                if changed:
                    obj.save(update_fields=['name', 'category', 'is_active', 'updated_at'])
                    updated += 1
                else:
                    skipped += 1

        self.stdout.write(self.style.SUCCESS(
            f'\nDone. Created: {created}  Updated: {updated}  Skipped: {skipped}'))

        # Seed straightforward conversions as well
        from django.db import transaction
        from catalog.models import UnitConversion
        from decimal import Decimal

        conv_created = conv_updated = 0
        for from_abbr, to_abbr, factor_str in COMMON_CONVERSIONS:
            from_u = Unit.all_objects.filter(abbreviation=from_abbr).first()
            to_u = Unit.all_objects.filter(abbreviation=to_abbr).first()
            if not from_u or not to_u:
                self.stdout.write(self.style.WARNING(
                    f'  Skipped conversion {from_abbr} → {to_abbr} because unit missing.'))
                continue
            factor = Decimal(factor_str)
            qs = UnitConversion.objects.filter(from_unit=from_u, to_unit=to_u)
            if qs.exists():
                conv = qs.first()
                if conv.factor != factor:
                    conv.factor = factor
                    conv.save(update_fields=['factor', 'updated_at'])
                    conv_updated += 1
                    self.stdout.write(self.style.WARNING(
                        f'  Updated conversion {from_abbr} → {to_abbr} = {factor}'))
            else:
                UnitConversion.objects.create(
                    from_unit=from_u, to_unit=to_u, factor=factor)
                conv_created += 1
                self.stdout.write(self.style.SUCCESS(
                    f'  Created conversion {from_abbr} → {to_abbr} = {factor}'))

        if conv_created or conv_updated:
            self.stdout.write(self.style.SUCCESS(
                f'Conversions: Created {conv_created}  Updated {conv_updated}'))
