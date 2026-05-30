#!/usr/bin/env python
"""
Fix the ACC-E-48-HA item conversion issue.

The problem:
- Item has cost_price=1847.54 per roll, selling_price=185.00 per roll
- But selling_price should be per meter (the selling_unit)
- This causes negative profit

The solution:
1. Determine the roll-to-meter conversion factor
2. Add a UnitConversion record
3. Optionally update the selling_price to be per roll (if it's actually per meter)
"""

import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'inventory_system.settings')
django.setup()

from decimal import Decimal
from catalog.models import Item, Unit, UnitConversion

# Find the item
item = Item.objects.get(code='ACC-E-48-HA')
print(f"Item: {item.code} - {item.name}")
print(f"Current cost_price: {item.cost_price} per {item.default_unit.abbreviation}")
print(f"Current selling_price: {item.selling_price} per {item.default_unit.abbreviation}")
print(f"Default unit: {item.default_unit.abbreviation}")
print(f"Selling unit: {item.selling_unit.abbreviation}")

# Get units
roll = item.default_unit
meter = item.selling_unit

print("\n" + "=" * 80)
print("ANALYSIS")
print("=" * 80)

# The selling_price (185) is likely the per-meter price, not per-roll
# We need to determine how many meters are in a roll

# Common roll sizes for wire mesh:
# - 30 meters per roll
# - 50 meters per roll  
# - 100 meters per roll

print("\nAssuming selling_price (185) is actually per METER:")
print("\nPossible scenarios:")

for meters_per_roll in [10, 20, 30, 50, 100]:
    selling_per_roll = Decimal('185') * Decimal(str(meters_per_roll))
    cost_per_roll = item.cost_price
    profit_per_roll = selling_per_roll - cost_per_roll
    margin = (profit_per_roll / selling_per_roll * 100) if selling_per_roll > 0 else Decimal('0')
    
    print(f"\nIf 1 roll = {meters_per_roll} meters:")
    print(f"  Selling price per roll: {selling_per_roll}")
    print(f"  Cost price per roll: {cost_per_roll}")
    print(f"  Profit per roll: {profit_per_roll}")
    print(f"  Margin: {margin:.1f}%")
    
    if 20 <= margin <= 50:
        print(f"  ✓ This looks reasonable!")

print("\n" + "=" * 80)
print("RECOMMENDED FIX")
print("=" * 80)

# Most likely scenario: 10 meters per roll (gives 10% margin)
meters_per_roll = 10
selling_per_meter = Decimal('185')
cost_per_meter = item.cost_price / Decimal(str(meters_per_roll))

print(f"\nBased on the analysis, assuming 1 roll = {meters_per_roll} meters:")
print(f"  Selling price per meter: {selling_per_meter}")
print(f"  Cost price per meter: {cost_per_meter:.2f}")
print(f"  Profit per meter: {selling_per_meter - cost_per_meter:.2f}")

print("\nTo fix this issue, you need to:")
print(f"1. Add a UnitConversion: roll → meter, factor={meters_per_roll}")
print(f"2. Set conversion_price={selling_per_meter} (the per-meter selling price)")
print(f"3. Update item.selling_price to {selling_per_meter * meters_per_roll} (per roll)")

print("\n" + "=" * 80)
response = input("\nDo you want to apply this fix? (yes/no): ")

if response.lower() == 'yes':
    # Create the conversion
    conversion, created = UnitConversion.objects.get_or_create(
        from_unit=roll,
        to_unit=meter,
        item=item,
        defaults={
            'factor': Decimal(str(meters_per_roll)),
            'conversion_price': selling_per_meter,
        }
    )
    
    if created:
        print(f"\n✓ Created UnitConversion: 1 {roll.abbreviation} = {meters_per_roll} {meter.abbreviation}")
        print(f"  Conversion price: {selling_per_meter} per {meter.abbreviation}")
    else:
        print(f"\n✓ UnitConversion already exists")
    
    # Update the item's selling_price to be per roll
    new_selling_price = selling_per_meter * Decimal(str(meters_per_roll))
    item.selling_price = new_selling_price
    item.save(update_fields=['selling_price'])
    
    print(f"✓ Updated item.selling_price to {new_selling_price} per {roll.abbreviation}")
    
    print("\n" + "=" * 80)
    print("FIX APPLIED SUCCESSFULLY!")
    print("=" * 80)
    print("\nNow when you create a sales order:")
    print(f"  - Selling 1 meter will show price: {selling_per_meter}")
    print(f"  - COGS per meter: {cost_per_meter:.2f}")
    print(f"  - Profit per meter: {selling_per_meter - cost_per_meter:.2f}")
else:
    print("\nFix not applied. Please manually review and fix the item.")
