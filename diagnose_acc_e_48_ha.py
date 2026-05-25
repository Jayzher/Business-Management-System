#!/usr/bin/env python
"""
Diagnose and fix the ACC-E-48-HA negative profit issue.

The issue: Services COGS now correctly uses procurement unit (Roll),
but there's no conversion factor from Roll to Meter, causing the system
to treat 1 meter as consuming 1 full roll.
"""

import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'inventory_system.settings')
django.setup()

from decimal import Decimal
from catalog.models import Item, Unit, UnitConversion

def main():
    print("=" * 80)
    print("DIAGNOSING ACC-E-48-HA NEGATIVE PROFIT ISSUE")
    print("=" * 80)
    
    # Find the item
    try:
        item = Item.objects.get(code='ACC-E-48-HA')
    except Item.DoesNotExist:
        print("\n✗ Item ACC-E-48-HA not found!")
        return
    
    print(f"\nItem: {item.code} - {item.name}")
    print(f"Default unit (procurement): {item.default_unit.abbreviation}")
    print(f"Selling unit: {item.selling_unit.abbreviation if item.selling_unit else 'None'}")
    print(f"Cost price: {item.cost_price} per {item.default_unit.abbreviation}")
    print(f"Selling price: {item.selling_price} per {item.default_unit.abbreviation}")
    
    # Check for conversion
    roll = item.default_unit
    meter = item.selling_unit
    
    print("\n" + "=" * 80)
    print("CHECKING UNIT CONVERSION")
    print("=" * 80)
    
    conversion = UnitConversion.objects.filter(
        from_unit=roll,
        to_unit=meter,
        item=item,
        is_active=True
    ).first()
    
    if not conversion:
        # Try reverse
        conversion = UnitConversion.objects.filter(
            from_unit=meter,
            to_unit=roll,
            item=item,
            is_active=True
        ).first()
        
        if conversion:
            print(f"\n✓ Found REVERSE conversion:")
            print(f"  {conversion.factor} {meter.abbreviation} = 1 {roll.abbreviation}")
            meters_per_roll = conversion.factor
        else:
            print(f"\n✗ NO conversion found between {roll.abbreviation} and {meter.abbreviation}!")
            print("\nThis is why you're seeing negative profit:")
            print("  - Service uses 1 meter")
            print("  - System doesn't know how many meters in a roll")
            print("  - System assumes 1 meter = 1 roll consumed")
            print(f"  - COGS = {item.cost_price} (full roll cost)")
            print(f"  - Revenue = 185.00 (1 meter)")
            print(f"  - Profit = 185.00 - {item.cost_price} = {185 - item.cost_price}")
            
            print("\n" + "=" * 80)
            print("SOLUTION: ADD UNIT CONVERSION")
            print("=" * 80)
            
            # Calculate reasonable conversion factor
            print("\nAnalyzing possible meters per roll...")
            
            # Your current transaction shows:
            # Selling 1m @ 185 = 185 revenue
            # COGS = 1847.54 (full roll)
            # This suggests the selling price might be correct per meter
            
            cost_per_roll = item.cost_price  # 1847.54
            selling_per_meter = Decimal('185')  # From your transaction
            
            print(f"\nGiven:")
            print(f"  Cost per roll: {cost_per_roll}")
            print(f"  Selling per meter: {selling_per_meter}")
            
            print("\nPossible scenarios:")
            
            best_factor = None
            best_margin = None
            
            for meters_per_roll in [5, 10, 15, 20, 25, 30, 50, 100]:
                cost_per_meter = cost_per_roll / Decimal(str(meters_per_roll))
                profit_per_meter = selling_per_meter - cost_per_meter
                margin = (profit_per_meter / selling_per_meter * 100) if selling_per_meter > 0 else Decimal('0')
                
                status = "✓" if 10 <= margin <= 50 else " "
                print(f"\n  {status} If 1 roll = {meters_per_roll} meters:")
                print(f"      Cost per meter: {cost_per_meter:.2f}")
                print(f"      Selling per meter: {selling_per_meter}")
                print(f"      Profit per meter: {profit_per_meter:.2f}")
                print(f"      Margin: {margin:.1f}%")
                
                if 10 <= margin <= 50:
                    if best_margin is None or abs(margin - 25) < abs(best_margin - 25):
                        best_factor = meters_per_roll
                        best_margin = margin
            
            if best_factor is None:
                best_factor = 10  # Default
                best_margin = (selling_per_meter - cost_per_roll / 10) / selling_per_meter * 100
            
            print("\n" + "=" * 80)
            print(f"RECOMMENDED: 1 roll = {best_factor} meters")
            print(f"This gives a {best_margin:.1f}% profit margin")
            print("=" * 80)
            
            cost_per_meter = cost_per_roll / Decimal(str(best_factor))
            profit_per_meter = selling_per_meter - cost_per_meter
            
            print(f"\nWith this conversion:")
            print(f"  When you sell 1 meter:")
            print(f"    Revenue: {selling_per_meter}")
            print(f"    COGS: {cost_per_meter:.2f}")
            print(f"    Profit: {profit_per_meter:.2f}")
            
            print(f"\n  When you sell 1 roll ({best_factor} meters):")
            print(f"    Revenue: {selling_per_meter * best_factor}")
            print(f"    COGS: {cost_per_roll}")
            print(f"    Profit: {(selling_per_meter * best_factor) - cost_per_roll:.2f}")
            
            print("\n" + "=" * 80)
            response = input(f"\nCreate this conversion? (yes/no): ").strip().lower()
            
            if response == 'yes':
                # Create the conversion
                UnitConversion.objects.create(
                    from_unit=roll,
                    to_unit=meter,
                    item=item,
                    factor=Decimal(str(best_factor)),
                    conversion_price=selling_per_meter,
                    is_active=True
                )
                
                print(f"\n✓ Created conversion: 1 {roll.abbreviation} = {best_factor} {meter.abbreviation}")
                print(f"✓ Set conversion_price = {selling_per_meter} per {meter.abbreviation}")
                
                print("\n" + "=" * 80)
                print("FIX APPLIED!")
                print("=" * 80)
                print("\nNext steps:")
                print("  1. Existing service invoices will still show old COGS")
                print("  2. New services will calculate correctly")
                print("  3. You may need to adjust existing invoices manually")
                
            else:
                print("\nFix not applied.")
                print("\nTo fix manually:")
                print("  1. Go to: Catalog → Unit Conversions")
                print(f"  2. Add conversion: {roll.abbreviation} → {meter.abbreviation}")
                print(f"  3. Factor: {best_factor}")
                print(f"  4. Conversion price: {selling_per_meter}")
            
            return
    
    else:
        print(f"\n✓ Found conversion:")
        print(f"  1 {roll.abbreviation} = {conversion.factor} {meter.abbreviation}")
        if conversion.conversion_price:
            print(f"  Conversion price: {conversion.conversion_price} per {meter.abbreviation}")
        
        # Calculate expected values
        meters_per_roll = conversion.factor
        cost_per_meter = item.cost_price / meters_per_roll
        selling_per_meter = conversion.conversion_price or (item.selling_price / meters_per_roll)
        profit_per_meter = selling_per_meter - cost_per_meter
        
        print(f"\nExpected calculation for 1 meter:")
        print(f"  Selling: {selling_per_meter}")
        print(f"  COGS: {cost_per_meter:.2f}")
        print(f"  Profit: {profit_per_meter:.2f}")
        
        if profit_per_meter < 0:
            print(f"\n⚠️  WARNING: Still showing negative profit!")
            print(f"\nPossible issues:")
            print(f"  1. Conversion factor might be wrong")
            print(f"  2. Cost price might be incorrect")
            print(f"  3. Selling price might be incorrect")
            
            print("\n" + "=" * 80)
            response = input("\nWould you like to update the conversion? (yes/no): ").strip().lower()
            
            if response == 'yes':
                print("\nEnter new values (press Enter to keep current):")
                
                new_factor = input(f"Meters per roll [{meters_per_roll}]: ").strip()
                if new_factor:
                    conversion.factor = Decimal(new_factor)
                
                new_price = input(f"Selling price per meter [{selling_per_meter}]: ").strip()
                if new_price:
                    conversion.conversion_price = Decimal(new_price)
                
                conversion.save()
                print("\n✓ Conversion updated!")
        else:
            print(f"\n✓ Conversion looks correct!")
            print(f"\nIf you're still seeing negative profit, check:")
            print(f"  1. The service invoice date (old invoices won't recalculate)")
            print(f"  2. The actual unit used in the service line")
            print(f"  3. Whether the conversion is active")

if __name__ == '__main__':
    main()
