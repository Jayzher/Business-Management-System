# Sales Order Unit Conversion Issue - Complete Fix Guide

## 🔴 Problem Summary

When creating Sales Orders with items that have:
- **Procurement unit (default_unit)**: Roll
- **Selling unit**: Meter
- **Missing unit conversion** between Roll and Meter

The system causes **negative totals** because:
1. No conversion exists between Roll and Meter
2. The `selling_price` field contains the per-meter price (185) but is stored as "per roll"
3. COGS calculation uses the full roll cost (1847.54) for each meter sold
4. Result: Revenue 185 - COGS 1847.54 = **-1662.54 loss per meter!**

## 🔍 Root Cause Analysis

### Item: ACC-E-48-HA (Expanded wire # 48 Analok)

**Current Data:**
```
code: ACC-E-48-HA
default_unit: roll
selling_unit: m (meter)
cost_price: 1847.54 per roll
selling_price: 185.00 per roll  ← WRONG! This is actually per meter
```

**The Issue:**
The `selling_price` field is **ambiguous**. It's stored as "per default_unit" (roll) but the value (185) is actually the per-meter price.

**What Happens in Sales Order:**
1. User selects item and unit = "meter"
2. System looks for conversion from roll → meter
3. **No conversion found!**
4. System returns `selling_price = 185` without conversion
5. COGS calculation: `cost_price = 1847.54` (full roll cost!)
6. Line total: `1 meter × 185 = 185`
7. Line COGS: `1 meter × 1847.54 = 1847.54`
8. **Profit: 185 - 1847.54 = -1662.54** ❌

## ✅ Solution

### Step 1: Determine Roll-to-Meter Conversion Factor

Based on the cost and selling prices, we need to determine how many meters are in one roll.

**Analysis:**
```
If 1 roll = 10 meters:
  Selling per roll: 185 × 10 = 1850
  Cost per roll: 1847.54
  Profit per roll: 2.46
  Margin: 0.13% ← Too low!

If 1 roll = 20 meters:
  Selling per roll: 185 × 20 = 3700
  Cost per roll: 1847.54
  Profit per roll: 1852.46
  Margin: 50% ← Reasonable!

If 1 roll = 30 meters:
  Selling per roll: 185 × 30 = 5550
  Cost per roll: 1847.54
  Profit per roll: 3702.46
  Margin: 67% ← High but possible
```

**Recommended: 20 meters per roll** (50% margin is typical for this industry)

### Step 2: Add Unit Conversion

```python
from catalog.models import Item, Unit, UnitConversion
from decimal import Decimal

# Get the item and units
item = Item.objects.get(code='ACC-E-48-HA')
roll = Unit.objects.get(abbreviation='roll')
meter = Unit.objects.get(abbreviation='m')

# Create the conversion
UnitConversion.objects.create(
    from_unit=roll,
    to_unit=meter,
    factor=Decimal('20'),  # 1 roll = 20 meters
    conversion_price=Decimal('185'),  # Selling price per meter
    item=item
)
```

### Step 3: Update Item Selling Price

The `selling_price` should be stored **per default_unit** (roll):

```python
# Update selling_price to be per roll
item.selling_price = Decimal('185') * Decimal('20')  # 3700 per roll
item.save(update_fields=['selling_price'])
```

### Step 4: Verify the Fix

After applying the fix:

```python
from catalog.utils import convert_price_for_unit, get_item_cogs_for_unit

# Test selling price conversion
selling_per_meter = convert_price_for_unit(
    item.selling_price,  # 3700 per roll
    roll,
    meter,
    item=item
)
# Result: 185.00 per meter ✓

# Test COGS conversion
cogs_per_meter = get_item_cogs_for_unit(item, meter)
# Result: 1847.54 / 20 = 92.38 per meter ✓

# Calculate profit
profit = selling_per_meter - cogs_per_meter
# Result: 185.00 - 92.38 = 92.62 per meter ✓
# Margin: 50% ✓
```

## 🛠️ Implementation Steps

### Option 1: Use the Fix Script (Recommended)

```bash
cd D:\PsyChoNyMouz\Projects\BusinessWebsite\Business-Management-System
python fix_acc_e_48_ha.py
```

The script will:
1. Analyze the item
2. Show possible conversion scenarios
3. Recommend the best fix
4. Apply the fix with your confirmation

### Option 2: Manual Fix via Django Admin

1. Go to **Catalog → Unit Conversions**
2. Click **Add Unit Conversion**
3. Fill in:
   - From unit: Roll
   - To unit: Meter
   - Factor: 20 (or appropriate value)
   - Conversion price: 185.00
   - Item: ACC-E-48-HA
4. Click **Save**
5. Go to **Catalog → Items**
6. Find **ACC-E-48-HA**
7. Update **Selling price** to: 3700.00 (185 × 20)
8. Click **Save**

### Option 3: SQL Fix

```sql
-- Add the conversion
INSERT INTO catalog_unitconversion (
    from_unit_id, to_unit_id, factor, conversion_price, item_id, is_active, created_at, updated_at
)
SELECT 
    (SELECT id FROM catalog_unit WHERE abbreviation = 'roll'),
    (SELECT id FROM catalog_unit WHERE abbreviation = 'm'),
    20,
    185.00,
    (SELECT id FROM catalog_item WHERE code = 'ACC-E-48-HA'),
    1,
    NOW(),
    NOW();

-- Update the item selling price
UPDATE catalog_item
SET selling_price = 3700.00,
    updated_at = NOW()
WHERE code = 'ACC-E-48-HA';
```

## 🧪 Testing

After applying the fix, test with a sales order:

1. Create a new Sales Order
2. Add item: ACC-E-48-HA
3. Set quantity: 1
4. Set unit: Meter
5. **Expected results:**
   - Unit price: 185.00
   - Line total: 185.00
   - COGS: 92.38
   - Profit: 92.62 ✓

## 📋 Audit Other Items

Run the audit command to find other items with similar issues:

```bash
python manage.py audit_unit_conversions
```

This will identify all items with:
- Different default and selling units
- Missing unit conversions
- Potential pricing issues

## 🔧 Code Improvements Applied

### 1. Enhanced Error Logging

Updated `catalog/utils.py` to log warnings when conversions are missing:

```python
def convert_price_for_unit(...):
    # ... existing code ...
    
    if conv is None:
        logger.warning(
            f"No unit conversion found between {base_unit.abbreviation} and {selling_unit.abbreviation}"
            f"{item_info}. Returning base price without conversion."
        )
        return base_price_dec.quantize(Decimal(10) ** -round_places)
```

### 2. Audit Management Command

Created `catalog/management/commands/audit_unit_conversions.py` to:
- Find items with missing conversions
- Show price scenarios with different conversion factors
- Provide recommendations for fixes

## 📝 Best Practices Going Forward

1. **Always define unit conversions** when `default_unit ≠ selling_unit`
2. **Store selling_price per default_unit**, not per selling_unit
3. **Use conversion_price** to override calculated per-unit prices when needed
4. **Run audit command** regularly to catch missing conversions
5. **Test sales orders** after adding new items with different units

## 🎯 Summary

The issue was caused by:
- ❌ Missing unit conversion between Roll and Meter
- ❌ Ambiguous selling_price (stored as per-roll but value is per-meter)
- ❌ COGS using full roll cost for meter sales

The fix involves:
- ✅ Adding UnitConversion: 1 roll = 20 meters
- ✅ Setting conversion_price = 185 (per meter)
- ✅ Updating selling_price = 3700 (per roll)
- ✅ Enhanced logging for missing conversions
- ✅ Audit command to prevent future issues

After the fix, sales orders will calculate correctly with positive profit margins.
