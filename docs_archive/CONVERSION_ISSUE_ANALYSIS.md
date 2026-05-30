# Sales Order Unit Conversion Issue Analysis

## Problem Description
When creating a Sales Order with items that have:
- **Procurement unit (default_unit/stock_unit)**: Roll
- **Selling unit**: Meter  
- **No direct unit conversion** between Roll and Meter

The system miscalculates prices, causing **negative totals** even for a single meter sale.

## Root Cause

### Issue 1: Missing Unit Conversions
Many items have `default_unit=roll` and `selling_unit=m` but there's **NO conversion** defined between Roll and Meter in the `UnitConversion` table.

Example items affected:
- `ACC-E-48-HA`: cost=1847.54/roll, selling=185.00/roll, selling_unit=m
- `ACC-S-48-HA-SKY`: cost=1920.77/roll, selling=165.00/roll, selling_unit=m

### Issue 2: Price Interpretation Error
When `selling_price=185.00` is stored on an item with:
- `default_unit=roll`
- `selling_unit=m`

The system is **ambiguous** about whether 185.00 is:
1. Per Roll (the default_unit) ✓ CORRECT
2. Per Meter (the selling_unit) ✗ WRONG

Currently, the system treats it as "per roll" but when selling in meters without a conversion, it applies the full roll price to each meter, causing massive overcharging.

### Issue 3: COGS Calculation
When calculating COGS for a meter sale:
- Cost price: 1847.54 per roll
- Without conversion factor, COGS per meter = 1847.54 (WRONG!)
- Selling price per meter = 185.00 (if conversion_price is set) or 185.00 (if no conversion)
- **Result: Negative profit** (185 - 1847.54 = -1662.54)

## Solution

### Option 1: Add Missing Unit Conversions (RECOMMENDED)
For each item with `default_unit=roll` and `selling_unit=m`, add a `UnitConversion` record:

```python
# Example for ACC-E-48-HA
# If 1 roll = 50 meters
UnitConversion.objects.create(
    from_unit=roll,
    to_unit=meter,
    factor=50,  # 1 roll = 50 meters
    conversion_price=185.00,  # Selling price per roll (will be divided by factor for per-meter price)
    item=item_ACC_E_48_HA
)
```

**Calculation with conversion:**
- Selling price per meter: 185.00 / 50 = 3.70 per meter
- COGS per meter: 1847.54 / 50 = 36.95 per meter
- Profit per meter: 3.70 - 36.95 = **-33.25 per meter** (STILL NEGATIVE!)

This reveals the **real problem**: The selling price (185/roll) is LESS than the cost price (1847.54/roll), indicating a **data entry error** or the selling_price field contains the wrong value.

### Option 2: Fix Item Data
The `selling_price` field should contain the price **per default_unit** (roll), not per selling_unit (meter).

If the item sells for 185 per meter and there are 50 meters per roll:
```python
item.selling_price = 185 * 50  # 9250 per roll
item.cost_price = 1847.54  # per roll
# Profit per roll: 9250 - 1847.54 = 7402.46 ✓
```

Then with conversion:
- Selling price per meter: 9250 / 50 = 185.00 per meter ✓
- COGS per meter: 1847.54 / 50 = 36.95 per meter ✓
- Profit per meter: 185.00 - 36.95 = 148.05 per meter ✓

## Recommended Actions

1. **Audit all items** with `default_unit != selling_unit`
2. **Verify selling_price** is stored per default_unit, not per selling_unit
3. **Add missing UnitConversion** records for all roll→meter items
4. **Set conversion_price** to the actual per-meter selling price if different from calculated
5. **Test calculations** before and after to ensure profit margins are correct

## SQL Queries to Find Affected Items

```sql
-- Find items with different default and selling units but no conversion
SELECT 
    i.code,
    i.name,
    i.cost_price,
    i.selling_price,
    du.abbreviation as default_unit,
    su.abbreviation as selling_unit
FROM catalog_item i
JOIN catalog_unit du ON i.default_unit_id = du.id
LEFT JOIN catalog_unit su ON i.selling_unit_id = su.id
WHERE i.selling_unit_id IS NOT NULL 
  AND i.default_unit_id != i.selling_unit_id
  AND NOT EXISTS (
      SELECT 1 FROM catalog_unitconversion uc
      WHERE (uc.from_unit_id = i.default_unit_id AND uc.to_unit_id = i.selling_unit_id)
         OR (uc.from_unit_id = i.selling_unit_id AND uc.to_unit_id = i.default_unit_id)
  );
```

## Code Fix Required

Update `catalog/utils.py` `convert_price_for_unit()` to handle missing conversions gracefully:

```python
def convert_price_for_unit(...):
    # ... existing code ...
    
    conv, is_reverse = _lookup_conversion_record(base_unit, selling_unit, item)
    
    if conv is None:
        # NO CONVERSION FOUND - Log warning and return base price
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(
            f"No unit conversion found between {base_unit.abbreviation} and {selling_unit.abbreviation} "
            f"for item {item.code if item else 'N/A'}. Returning base price without conversion."
        )
        return base_price_dec.quantize(Decimal(10) ** -round_places)
    
    # ... rest of existing code ...
```

This will prevent silent calculation errors and alert administrators to missing conversions.
