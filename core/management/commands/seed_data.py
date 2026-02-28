"""
Management command to seed initial data: categories, units, roles, warehouse, sample items.
Usage: python manage.py seed_data
"""
from django.core.management.base import BaseCommand
from django.db import transaction


class Command(BaseCommand):
    help = 'Seed initial data for the inventory system'

    @transaction.atomic
    def handle(self, *args, **options):
        self._seed_roles()
        self._seed_units()
        self._seed_categories()
        self._seed_warehouse()
        self._seed_partners()
        self._seed_items()
        self.stdout.write(self.style.SUCCESS('Seed data loaded successfully.'))

    def _seed_roles(self):
        from accounts.models import Role
        roles = ['Admin', 'Warehouse Manager', 'Encoder', 'Checker', 'Viewer']
        for name in roles:
            Role.objects.get_or_create(name=name, defaults={'description': f'{name} role'})
        self.stdout.write(f'  Roles: {len(roles)}')

    def _seed_units(self):
        from catalog.models import Unit, UnitConversion
        units_data = [
            ('Piece', 'pcs'),
            ('Meter', 'm'),
            ('Kilogram', 'kg'),
            ('Sheet', 'sht'),
            ('Bar', 'bar'),
            ('Box', 'box'),
            ('Roll', 'roll'),
            ('Liter', 'L'),
            ('Set', 'set'),
        ]
        units = {}
        for name, abbr in units_data:
            u, _ = Unit.objects.get_or_create(abbreviation=abbr, defaults={'name': name})
            units[abbr] = u

        # Sample conversion: 1 box = 20 pcs
        if 'box' in units and 'pcs' in units:
            UnitConversion.objects.get_or_create(
                from_unit=units['box'], to_unit=units['pcs'],
                defaults={'factor': 20}
            )
        self.stdout.write(f'  Units: {len(units_data)}')

    def _seed_categories(self):
        from catalog.models import Category
        # Root categories
        raw, _ = Category.objects.get_or_create(code='RAW', defaults={'name': 'Raw Materials'})
        fin, _ = Category.objects.get_or_create(code='FIN', defaults={'name': 'Finished Products'})

        # Sub-categories under Raw Materials
        subs_raw = [
            ('RAW-ALU', 'Aluminum Profiles'),
            ('RAW-GLS', 'Glass Panels'),
            ('RAW-SEA', 'Sealants & Adhesives'),
            ('RAW-SCR', 'Screws & Fasteners'),
            ('RAW-ACC', 'Accessories'),
        ]
        for code, name in subs_raw:
            Category.objects.get_or_create(code=code, defaults={'name': name, 'parent': raw})

        # Sub-categories under Finished Products
        subs_fin = [
            ('FIN-FUR', 'Aluminum Furniture'),
            ('FIN-WIN', 'Windows & Doors'),
            ('FIN-ASM', 'Assembled Units'),
        ]
        for code, name in subs_fin:
            Category.objects.get_or_create(code=code, defaults={'name': name, 'parent': fin})

        self.stdout.write(f'  Categories: {2 + len(subs_raw) + len(subs_fin)}')

    def _seed_warehouse(self):
        from warehouses.models import Warehouse, Location
        wh, _ = Warehouse.objects.get_or_create(
            code='WH-MAIN',
            defaults={'name': 'Main Warehouse', 'city': 'Manila'}
        )
        # Create zones and bins
        zone_a, _ = Location.objects.get_or_create(
            warehouse=wh, code='ZONE-A',
            defaults={'name': 'Zone A - Raw Materials', 'location_type': 'ZONE', 'is_pickable': False}
        )
        zone_b, _ = Location.objects.get_or_create(
            warehouse=wh, code='ZONE-B',
            defaults={'name': 'Zone B - Finished Products', 'location_type': 'ZONE', 'is_pickable': False}
        )
        # Bins under Zone A
        for i in range(1, 6):
            Location.objects.get_or_create(
                warehouse=wh, code=f'A-R1-B{i}',
                defaults={
                    'name': f'Rack 1 Bin {i}',
                    'parent': zone_a,
                    'location_type': 'BIN',
                    'is_pickable': True,
                }
            )
        # Bins under Zone B
        for i in range(1, 4):
            Location.objects.get_or_create(
                warehouse=wh, code=f'B-R1-B{i}',
                defaults={
                    'name': f'Rack 1 Bin {i}',
                    'parent': zone_b,
                    'location_type': 'BIN',
                    'is_pickable': True,
                }
            )
        self.stdout.write(f'  Warehouse: {wh.code} with locations')

    def _seed_partners(self):
        from partners.models import Supplier, Customer
        suppliers = [
            ('SUP-001', 'Aluminum Corp PH', 'Manila'),
            ('SUP-002', 'GlassTech Industries', 'Cebu'),
            ('SUP-003', 'FastenAll Supply', 'Davao'),
        ]
        for code, name, city in suppliers:
            Supplier.objects.get_or_create(code=code, defaults={'name': name, 'city': city})

        customers = [
            ('CUS-001', 'Metro Construction Inc', 'Manila'),
            ('CUS-002', 'HomeStyle Interiors', 'Quezon City'),
            ('CUS-003', 'BuildRight Corp', 'Makati'),
        ]
        for code, name, city in customers:
            Customer.objects.get_or_create(code=code, defaults={'name': name, 'city': city})

        self.stdout.write(f'  Partners: {len(suppliers)} suppliers, {len(customers)} customers')

    def _seed_items(self):
        from catalog.models import Item, Category, Unit, MaterialSpec, ProductSpec

        pcs = Unit.objects.get(abbreviation='pcs')
        m = Unit.objects.get(abbreviation='m')
        sht = Unit.objects.get(abbreviation='sht')
        kg = Unit.objects.get(abbreviation='kg')
        bar_unit = Unit.objects.get(abbreviation='bar')

        cat_alu = Category.objects.get(code='RAW-ALU')
        cat_gls = Category.objects.get(code='RAW-GLS')
        cat_scr = Category.objects.get(code='RAW-SCR')
        cat_fur = Category.objects.get(code='FIN-FUR')
        cat_win = Category.objects.get(code='FIN-WIN')

        raw_items = [
            ('ALU-6063-T5', 'Aluminum Profile 6063-T5', cat_alu, bar_unit, {'alloy': '6063-T5', 'length': 6.0, 'thickness': 1.2}),
            ('ALU-6061-T6', 'Aluminum Profile 6061-T6', cat_alu, bar_unit, {'alloy': '6061-T6', 'length': 6.0, 'thickness': 1.5}),
            ('GLS-CLR-6MM', 'Clear Glass 6mm', cat_gls, sht, {'thickness': 6.0, 'length': 2.44, 'width': 1.22}),
            ('GLS-TMD-8MM', 'Tempered Glass 8mm', cat_gls, sht, {'thickness': 8.0, 'length': 2.44, 'width': 1.22}),
            ('SCR-SS-M6', 'Stainless Steel Screw M6x25', cat_scr, pcs, {}),
            ('SCR-SS-M8', 'Stainless Steel Screw M8x30', cat_scr, pcs, {}),
        ]
        for code, name, cat, unit, spec_data in raw_items:
            item, created = Item.objects.get_or_create(
                code=code,
                defaults={
                    'name': name, 'item_type': 'RAW', 'category': cat,
                    'default_unit': unit, 'reorder_point': 10,
                }
            )
            if created and spec_data:
                MaterialSpec.objects.create(item=item, **spec_data)

        fin_items = [
            ('FUR-TBL-001', 'Aluminum Dining Table', cat_fur, pcs, {'model_name': 'DT-100', 'dimensions': '120x80x75cm'}),
            ('FUR-CHR-001', 'Aluminum Chair', cat_fur, pcs, {'model_name': 'CH-200', 'dimensions': '45x45x90cm'}),
            ('WIN-SLD-001', 'Sliding Window 120x100', cat_win, pcs, {'model_name': 'SW-120', 'dimensions': '120x100cm'}),
        ]
        for code, name, cat, unit, spec_data in fin_items:
            item, created = Item.objects.get_or_create(
                code=code,
                defaults={
                    'name': name, 'item_type': 'FINISHED', 'category': cat,
                    'default_unit': unit, 'reorder_point': 5,
                }
            )
            if created and spec_data:
                ProductSpec.objects.create(item=item, **spec_data)

        self.stdout.write(f'  Items: {len(raw_items)} raw + {len(fin_items)} finished')
