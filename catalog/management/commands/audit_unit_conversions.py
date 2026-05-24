"""
Management command to audit items with missing unit conversions.

Usage:
    python manage.py audit_unit_conversions
    python manage.py audit_unit_conversions --fix
"""
from django.core.management.base import BaseCommand
from django.db.models import F
from decimal import Decimal
from catalog.models import Item, UnitConversion


class Command(BaseCommand):
    help = 'Audit items with different default and selling units for missing conversions'

    def add_arguments(self, parser):
        parser.add_argument(
            '--fix',
            action='store_true',
            help='Attempt to create missing conversions (requires manual factor input)',
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('=' * 80))
        self.stdout.write(self.style.SUCCESS('UNIT CONVERSION AUDIT'))
        self.stdout.write(self.style.SUCCESS('=' * 80))

        # Find items with different default and selling units
        items = Item.objects.select_related(
            'default_unit', 'selling_unit'
        ).exclude(
            selling_unit__isnull=True
        ).exclude(
            default_unit=F('selling_unit')
        ).order_by('code')

        if not items:
            self.stdout.write(self.style.SUCCESS('\n✓ No items found with different default and selling units.'))
            return

        self.stdout.write(f'\nFound {items.count()} items with different default and selling units.\n')

        issues = []
        for item in items:
            # Check if conversion exists
            has_conversion = UnitConversion.objects.filter(
                from_unit=item.default_unit,
                to_unit=item.selling_unit,
                item=item
            ).exists() or UnitConversion.objects.filter(
                from_unit=item.selling_unit,
                to_unit=item.default_unit,
                item=item
            ).exists()

            if not has_conversion:
                # Check for global conversion
                has_global = UnitConversion.objects.filter(
                    from_unit=item.default_unit,
                    to_unit=item.selling_unit,
                    item__isnull=True
                ).exists() or UnitConversion.objects.filter(
                    from_unit=item.selling_unit,
                    to_unit=item.default_unit,
                    item__isnull=True
                ).exists()

                issues.append({
                    'item': item,
                    'has_global': has_global
                })

        if not issues:
            self.stdout.write(self.style.SUCCESS('✓ All items have unit conversions defined.'))
            return

        self.stdout.write(self.style.WARNING(f'\n⚠ Found {len(issues)} items WITHOUT unit conversions:\n'))

        for issue in issues:
            item = issue['item']
            has_global = issue['has_global']

            self.stdout.write(f'\n{self.style.WARNING("Item:")} {item.code} - {item.name}')
            self.stdout.write(f'  Default unit: {item.default_unit.abbreviation} ({item.default_unit.name})')
            self.stdout.write(f'  Selling unit: {item.selling_unit.abbreviation} ({item.selling_unit.name})')
            self.stdout.write(f'  Cost price: {item.cost_price} per {item.default_unit.abbreviation}')
            self.stdout.write(f'  Selling price: {item.selling_price} per {item.default_unit.abbreviation}')

            if has_global:
                self.stdout.write(self.style.SUCCESS(f'  ✓ Global conversion exists'))
            else:
                self.stdout.write(self.style.ERROR(f'  ✗ NO conversion found (item-specific or global)'))

            # Calculate what the per-selling-unit prices would be with different factors
            self.stdout.write(f'\n  {self.style.WARNING("Price scenarios:")}')
            for factor in [1, 10, 20, 50, 100]:
                selling_per_unit = item.selling_price / Decimal(str(factor))
                cost_per_unit = item.cost_price / Decimal(str(factor))
                profit = selling_per_unit - cost_per_unit
                profit_pct = (profit / cost_per_unit * 100) if cost_per_unit > 0 else Decimal('0')

                status = '✓' if profit > 0 else '✗'
                color = self.style.SUCCESS if profit > 0 else self.style.ERROR

                self.stdout.write(
                    f'    If 1 {item.default_unit.abbreviation} = {factor} {item.selling_unit.abbreviation}:'
                )
                self.stdout.write(
                    f'      Selling: {selling_per_unit:.2f}/{item.selling_unit.abbreviation}, '
                    f'Cost: {cost_per_unit:.2f}/{item.selling_unit.abbreviation}, '
                    f'Profit: {color(f"{profit:.2f} ({profit_pct:.1f}%) {status}")}'
                )

        self.stdout.write(f'\n{self.style.SUCCESS("=" * 80)}')
        self.stdout.write(f'{self.style.WARNING("RECOMMENDATIONS:")}')
        self.stdout.write('1. Add UnitConversion records for items without conversions')
        self.stdout.write('2. Verify selling_price is stored per default_unit, not per selling_unit')
        self.stdout.write('3. Use conversion_price field to override calculated per-unit prices if needed')
        self.stdout.write('4. Test sales orders after adding conversions to ensure correct calculations')
        self.stdout.write(f'{self.style.SUCCESS("=" * 80)}\n')
