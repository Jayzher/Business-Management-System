"""
Management command: calculate_inventory_value
==============================================
Calculates the total inventory asset value based on current stock balances
and weighted average cost.

This value represents the company's inventory assets (cash converted to goods
that haven't been sold yet).

Usage:
    python manage.py calculate_inventory_value
    python manage.py calculate_inventory_value --as-of 2024-03-31
"""
from decimal import Decimal
from datetime import date

from django.core.management.base import BaseCommand
from django.db.models import Sum, F

from inventory.models import StockBalance
from catalog.models import Item


class Command(BaseCommand):
    help = 'Calculate total inventory asset value at cost'

    def add_arguments(self, parser):
        parser.add_argument(
            '--as-of',
            type=str,
            help='Calculate inventory value as of specific date (YYYY-MM-DD)',
        )

    def handle(self, *args, **options):
        as_of_str = options.get('as_of')
        
        if as_of_str:
            try:
                as_of_date = date.fromisoformat(as_of_str)
                self.stdout.write(f'Calculating inventory value as of {as_of_date}...\n')
            except ValueError:
                self.stdout.write(self.style.ERROR('Invalid date format. Use YYYY-MM-DD'))
                return
        else:
            as_of_date = None
            self.stdout.write('Calculating current inventory value...\n')

        total_value = Decimal('0')
        total_qty = Decimal('0')
        item_count = 0

        # Get all stock balances with positive quantity
        balances = StockBalance.objects.filter(
            qty_on_hand__gt=0
        ).select_related('item', 'location')

        for balance in balances:
            item = balance.item
            qty = balance.qty_on_hand
            
            # Use weighted average cost (stored in item.cost_price)
            cost_price = item.cost_price or Decimal('0')
            
            # Calculate value for this item/location
            value = qty * cost_price
            
            if value > 0:
                total_value += value
                total_qty += qty
                item_count += 1
                
                self.stdout.write(
                    f'  {item.code:<20} | Qty: {qty:>10.2f} | '
                    f'Cost: ₱{cost_price:>8.2f} | Value: ₱{value:>12.2f} | '
                    f'Loc: {balance.location.code}'
                )

        self.stdout.write('\n' + '=' * 80)
        self.stdout.write(self.style.SUCCESS(
            f'\nTotal Inventory Value: ₱{total_value:,.2f}'
        ))
        self.stdout.write(f'Total Items: {item_count}')
        self.stdout.write(f'Total Quantity: {total_qty:,.2f}\n')
