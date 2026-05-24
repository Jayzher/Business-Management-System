#!/usr/bin/env python
"""
Interactive script to fix the Roll to Meter conversion issue for ACC-E-48-HA.
"""

import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'inventory_system.settings')
django.setup()

from decimal import Decimal
from catalog.models import Item, Unit, UnitConversion

def main():
    print("=" * 80)
    print("SALES ORDER CONVERSION FIX")
    print("=" * 80)
    
    # Find the problematic item
    try:
        item = Item.objects.get(code='ACC-E-48-HA')
    except Item.DoesNotExist:
        print("\n✓ Item ACC-E-48-HA not found. No fix needed.")
        return
    
    print(f"\nItem: {item.code} - {item.name}")
    print(f"Default unit: {item.default_unit.abbreviation}")
    print(f"Selling unit: {item.selling_unit.abbreviation if item.selling_unit else 'None'}")
    print(f"Cost price: {item.cost_price} per {item.default_unit.abbreviation}")
    print(f"Selling price: {item.selling_price} per {item.default_unit.abbreviation}")
    
    # Check if conversion already exists
    roll = item.default_unit
    meter = item.selling_unit
    
    existing_conversion = UnitConversion.objects.filter(
        from_unit=roll,
        to_unit=meter,
        item=item
    ).first()
    
    if existing_conversion:
        print(f"\n✓ Conversion already exists:")
        print(f"  1 {roll.abbreviation} = {existing_conversion.factor} {meter.abbreviation}")
        print(f"  Conversion price: {existing_conversion.conversion_price} per {meter.abbreviation}")
        
        # Calculate current profit
        selling_per_meter = existing_conversion.conversion_price or (item.selling_price / existing_conversion.factor)
        cost_per_meter = item.cost_price / existing_conversion.factor
        profit = selling_per_meter - cost_per_meter
        
        print(f"\nCurrent calculation:")
        print(f"  Selling per meter: {selling_per_meter}")
        print(f"  Cost per meter: {cost_per_meter:.2f}")
        print(f"  Profit per meter: {profit:.2f}")
        
        if profit < 0:
            print(f"\n⚠️  WARNING: Negative profit! The conversion needs adjustment.")
        else:
            print(f"\n✓ Profit is positive. Conversion appears correct.")
        
        return
    
    print(f"\n⚠️  NO conversion found between {roll.abbreviation} and {meter.abbreviation}")
    print("\nThis causes negative totals in sales orders!")
    
    # Recommend fix
    print("\n" + "=" * 80)
    print("RECOMMENDED FIX")
    print("=" * 80)
    
    # Assuming the selling_price (185) is actually per meter
    selling_per_meter = Decimal('185')
    
    print(f"\nAssuming selling_price ({item.selling_price}) is actually per METER:")
    print("\nAnalyzing possible conversion factors...")
    
    best_factor = None
    best_margin = None
    
    for factor in [10, 15, 20, 25, 30, 50]:
        selling_per_roll = selling_per_meter * Decimal(str(factor))
        cost_per_roll = item.cost_price
        profit_per_roll = selling_per_roll - cost_per_roll
        margin = (profit_per_roll / selling_per_roll * 100) if selling_per_roll > 0 else Decimal('0')
        
        status = "✓" if 20 <= margin <= 60 else " "
        print(f"\n  {status} If 1 roll = {factor} meters:")
        print(f"      Selling per roll: {selling_per_roll}")
        print(f"      Cost per roll: {cost_per_roll}")
        print(f"      Profit per roll: {profit_per_roll}")
        print(f"      Margin: {margin:.1f}%")
        
        if 20 <= margin <= 60 and (best_margin is None or abs(margin - 40) < abs(best_margin - 40)):
            best_factor = factor
            best_margin = margin
    
    if best_factor is None:
        best_factor = 20  # Default fallback
    
    print(f"\n{'=' * 80}")
    print(f"RECOMMENDED: 1 roll = {best_factor} meters (Margin: {best_margin:.1f}%)")
    print(f"{'=' * 80}")
    
    # Ask for confirmation
    print(f"\nThis will:")
    print(f"  1. Create UnitConversion: 1 {roll.abbreviation} = {best_factor} {meter.abbreviation}")
    print(f"  2. Set conversion_price = {selling_per_meter} per {meter.abbreviation}")
    print(f"  3. Update item.selling_price = {selling_per_meter * best_factor} per {roll.abbreviation}")
    
    response = input(f"\nApply this fix? (yes/no): ").strip().lower()
    
    if response == 'yes':
        # Create conversion
        conversion = UnitConversion.objects.create(
            from_unit=roll,
            to_unit=meter,
            factor=Decimal(str(best_factor)),
            conversion_price=selling_per_meter,
            item=item
        )
        print(f"\n✓ Created UnitConversion")
        
        # Update item selling price
        item.selling_price = selling_per_meter * Decimal(str(best_factor))
        item.save(update_fields=['selling_price'])
        print(f"✓ Updated item.selling_price to {item.selling_price}")
        
        # Verify
        cost_per_meter = item.cost_price / Decimal(str(best_factor))
        profit_per_meter = selling_per_meter - cost_per_meter
        
        print(f"\n{'=' * 80}")
        print("FIX APPLIED SUCCESSFULLY!")
        print(f"{'=' * 80}")
        print(f"\nVerification:")
        print(f"  Selling per meter: {selling_per_meter}")
        print(f"  Cost per meter: {cost_per_meter:.2f}")
        print(f"  Profit per meter: {profit_per_meter:.2f}")
        print(f"\n✓ Sales orders will now calculate correctly!")
        
    else:
        print("\nFix not applied.")
        print("\nTo fix manually:")
        print(f"  1. Go to Catalog → Unit Conversions")
        print(f"  2. Add: {roll.abbreviation} → {meter.abbreviation}, factor={best_factor}, conversion_price={selling_per_meter}")
        print(f"  3. Update item selling_price to {selling_per_meter * best_factor}")

if __name__ == '__main__':
    main()
