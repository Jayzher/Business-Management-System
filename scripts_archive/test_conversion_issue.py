#!/usr/bin/env python
"""
Test script to reproduce the Roll to Meter conversion issue.

Scenario:
- Item: Fabric
- Procurement unit (stock_unit): Roll
- Selling unit: Meter
- Conversion: 1 Roll = 50 Meters
- Cost price: 1000 per Roll
- Selling price: 25 per Meter

Expected behavior:
- When selling 1 Meter:
  - Selling price: 25 (correct)
  - COGS: 1000 / 50 = 20 per Meter (correct)
  - Profit: 25 - 20 = 5 per Meter (correct)

Current issue:
- The conversion might be calculating incorrectly, causing negative totals
"""

import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'inventory_system.settings')
django.setup()

from decimal import Decimal
from catalog.models import Unit, UnitConversion, Item, Category
from catalog.utils import convert_price_for_unit, get_item_cogs_for_unit, calculate_line_cogs_with_conversion

# Test the conversion logic
def test_roll_to_meter_conversion():
    print("=" * 80)
    print("Testing Roll to Meter Conversion")
    print("=" * 80)
    
    # Find or create units
    try:
        roll = Unit.objects.get(abbreviation='roll')
    except Unit.DoesNotExist:
        roll = Unit.objects.create(name='Roll', abbreviation='roll', category='material')
    
    try:
        meter = Unit.objects.get(abbreviation='m')
    except Unit.DoesNotExist:
        meter = Unit.objects.create(name='Meter', abbreviation='m', category='length')
    
    # Check if conversion exists
    conversion = UnitConversion.objects.filter(
        from_unit=roll, to_unit=meter, item__isnull=True
    ).first()
    
    if conversion:
        print(f"\nConversion found: 1 {roll.abbreviation} = {conversion.factor} {meter.abbreviation}")
        print(f"Conversion price: {conversion.conversion_price}")
    else:
        print("\nNo conversion found between Roll and Meter")
        return
    
    # Find a test item
    items = Item.objects.filter(default_unit=roll, selling_unit=meter)[:1]
    if not items:
        print("\nNo items found with Roll as default_unit and Meter as selling_unit")
        return
    
    item = items[0]
    print(f"\nTest Item: {item.code} - {item.name}")
    print(f"Cost price: {item.cost_price} per {item.default_unit.abbreviation}")
    print(f"Selling price: {item.selling_price} per {item.default_unit.abbreviation}")
    print(f"Stock unit: {item.stock_unit.abbreviation}")
    print(f"Selling unit: {item.selling_unit.abbreviation if item.selling_unit else 'None'}")
    
    # Test selling price conversion
    print("\n" + "-" * 80)
    print("SELLING PRICE CONVERSION (Roll → Meter)")
    print("-" * 80)
    
    selling_price_per_meter = convert_price_for_unit(
        item.selling_price,
        item.stock_unit,  # Roll
        meter,  # Meter
        item=item,
        use_conversion_price=True  # Use conversion_price if set
    )
    print(f"Selling price per Meter: {selling_price_per_meter}")
    print(f"Calculation: {item.selling_price} / {conversion.factor} = {item.selling_price / conversion.factor}")
    if conversion.conversion_price:
        print(f"Conversion price override: {conversion.conversion_price}")
    
    # Test COGS conversion
    print("\n" + "-" * 80)
    print("COGS CONVERSION (Roll → Meter)")
    print("-" * 80)
    
    cogs_per_meter = get_item_cogs_for_unit(item, meter)
    print(f"COGS per Meter: {cogs_per_meter}")
    print(f"Calculation: {item.cost_price} / {conversion.factor} = {item.cost_price / conversion.factor}")
    
    # Test line COGS calculation
    print("\n" + "-" * 80)
    print("LINE COGS CALCULATION (1 Meter)")
    print("-" * 80)
    
    qty = Decimal('1')
    line_cogs = calculate_line_cogs_with_conversion(item, qty, meter)
    print(f"Line COGS for {qty} Meter: {line_cogs}")
    print(f"Calculation: {cogs_per_meter} × {qty} = {line_cogs}")
    
    # Calculate profit
    print("\n" + "-" * 80)
    print("PROFIT CALCULATION")
    print("-" * 80)
    
    line_revenue = selling_price_per_meter * qty
    profit = line_revenue - line_cogs
    print(f"Revenue: {line_revenue}")
    print(f"COGS: {line_cogs}")
    print(f"Profit: {profit}")
    
    if profit < 0:
        print("\n⚠️  WARNING: NEGATIVE PROFIT DETECTED!")
        print("This indicates a conversion calculation error.")
    else:
        print("\n✓ Profit is positive - conversion appears correct.")
    
    print("\n" + "=" * 80)

if __name__ == '__main__':
    test_roll_to_meter_conversion()
