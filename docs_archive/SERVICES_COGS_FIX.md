# Services COGS Unit Fix - CORRECTED

## Problem
Services COGS calculation was incorrectly using the **Procurement Unit** when it should use the **unit that the quantity is stored in** (`line.unit`).

## Root Cause - The Misunderstanding

The original issue description was misleading. The problem wasn't about which unit to use for COGS calculation, but about **matching the unit with the quantity**.

### The Actual Bug

In the code, we have:
- `line.qty` = quantity stored in `line.unit` (e.g., 1.00 Meters)
- `line.unit` = the unit selected by the user (e.g., Meter)

**The bug was:**
```python
# WRONG - Mismatched units
procurement_unit = line.item.stock_unit  # Roll
cogs = calculate_line_cogs_with_conversion(line.item, line.qty, procurement_unit)
# This calculates: cost of line.qty ROLLS
# But line.qty is in METERS, not Rolls!
```

**Example with ACC-E-48-HA:**
- Item cost: 1847.54 per Roll
- Line: qty=1.00, unit=Meter
- Buggy calculation: 1847.54 per Roll × 1.00 = 1847.54 (treating 1.00 as Rolls!)
- Result: COGS = 1847.54 ❌

### The Correct Approach

```python
# CORRECT - Matching units
cogs = calculate_line_cogs_with_conversion(line.item, line.qty, line.unit)
# This calculates: cost of line.qty in line.unit
# line.qty = 1.00, line.unit = Meter
# Result: cost per Meter × 1.00 Meters
```

**Example with ACC-E-48-HA:**
- Item cost: 1847.54 per Roll
- Conversion: 1 Roll = 18 Meters
- Line: qty=1.00, unit=Meter
- Correct calculation:
  - Cost per Meter = 1847.54 ÷ 18 = 102.64
  - COGS = 102.64 × 1.00 = 102.64 ✓
- Result: COGS = 102.64 ✓

## Solution

The fix is to use `line.unit` (the unit that matches `line.qty`) instead of trying to force the procurement unit.

### Files Changed

#### 1. `core/cogs.py` - `service_invoice_cogs()` function
**Reverted to original logic:**
- Use `line.unit` (the unit that `line.qty` is in)
- Use `pli.unit` (the unit that `pli.min_qty` is in)

#### 2. `services/views.py` - `service_detail_view()` P&L calculation
**Fixed to use:**
- `line.unit` for product line COGS
- `pli.unit` for bundle COGS

## Why This is Correct

The `calculate_line_cogs_with_conversion()` function handles the unit conversion internally:

```python
def calculate_line_cogs_with_conversion(item, qty, unit):
    # Get cost price in the specified unit
    unit_cost = get_item_cogs_for_unit(item, unit)
    # This converts from stock_unit to the specified unit
    
    # Multiply by quantity (both in the same unit now)
    return unit_cost × qty
```

**The function already converts from procurement unit to the specified unit**, so we just need to pass the unit that matches the quantity.

## Real-World Example

### Item Setup
- **Item:** ACC-E-48-HA (Expanded wire # 48 Analok)
- **Procurement Unit:** Roll
- **Selling Unit:** Meter
- **Cost Price:** 1847.54 per Roll
- **Conversion:** 1 Roll = 18 Meters

### Service Line
```
qty: 1.00
unit: Meter (m)
unit_price: 185.00
```

### COGS Calculation (After Fix)
```python
# Step 1: Get cost per meter
unit_cost = get_item_cogs_for_unit(item, Meter)
# Converts: 1847.54 per Roll → 1847.54 ÷ 18 = 102.64 per Meter

# Step 2: Multiply by quantity
cogs = 102.64 × 1.00 = 102.64

# Step 3: Calculate profit
profit = 185.00 - 102.64 = 82.36 ✓
```

## Summary

| Aspect | Wrong Approach | Correct Approach |
|--------|----------------|------------------|
| **Unit passed** | `item.stock_unit` (Roll) | `line.unit` (Meter) |
| **Quantity** | 1.00 (in Meters) | 1.00 (in Meters) |
| **Mismatch?** | YES - treating 1.00 as Rolls | NO - both in Meters |
| **COGS** | 1847.54 ❌ | 102.64 ✓ |
| **Profit** | -1662.54 ❌ | 82.36 ✓ |

## Key Insight

**The unit conversion happens INSIDE `get_item_cogs_for_unit()`**, not outside. We don't need to manually use the procurement unit - the function handles that automatically by converting from `item.stock_unit` to whatever unit we specify.

**Always pass the unit that matches the quantity you're multiplying by.**

