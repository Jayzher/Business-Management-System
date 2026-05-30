# COGS Calculation Comparison: Sales vs Services

## Key Difference

| Aspect | Sales | Services |
|--------|-------|----------|
| **Unit Used for COGS** | Selling Unit (line.unit) | Procurement Unit (item.stock_unit) |
| **Rationale** | Customer buys in selling unit | Parts consumed from inventory at procurement rate |
| **Example** | Sell 10 Feet of cable | Use 1 Roll of cable (which = 50 Feet) |

## Code Comparison

### Sales COGS (Unchanged - Correct)
```python
# In sales_order_cogs() - core/cogs.py
for line in sales_order.lines.all():
    if line.item and line.unit:
        # Uses line.unit (selling unit) ✓ CORRECT for Sales
        cogs = calculate_line_cogs_with_conversion(
            line.item, 
            line.qty_ordered, 
            line.unit  # <-- Selling unit
        )
        total += cogs
```

### Services COGS (Fixed)
```python
# In service_invoice_cogs() - core/cogs.py
for line in svc.lines.all():
    if line.item:
        # Uses item.stock_unit (procurement unit) ✓ CORRECT for Services
        procurement_unit = line.item.stock_unit
        cogs = calculate_line_cogs_with_conversion(
            line.item, 
            line.qty, 
            procurement_unit  # <-- Procurement unit (FIXED)
        )
        total += cogs
```

## Real-World Example

### Item Setup
- **Item:** Electrical Wire Cable
- **Procurement Unit:** Roll
- **Selling Unit:** Foot
- **Cost Price:** $100 per Roll
- **Selling Price:** $5 per Foot
- **Conversion:** 1 Roll = 50 Feet

### Sales Transaction (Uses Selling Unit)
```
Customer Order: 10 Feet @ $5/Foot
Revenue: 10 × $5 = $50

COGS Calculation:
- Cost per Foot = $100 ÷ 50 = $2/Foot
- COGS = 10 Feet × $2/Foot = $20
- Profit = $50 - $20 = $30
```
✓ **Correct:** Customer bought 10 feet, we calculate cost for 10 feet

### Service Transaction (Uses Procurement Unit)
```
Service Line: 10 Feet @ $5/Foot (for customer billing)
Revenue: 10 × $5 = $50

COGS Calculation (BEFORE FIX - WRONG):
- Cost per Foot = $100 ÷ 50 = $2/Foot
- COGS = 10 Feet × $2/Foot = $20 ✗
- Profit = $50 - $20 = $30 ✗

COGS Calculation (AFTER FIX - CORRECT):
- We consumed 1 Roll from inventory
- Cost per Roll = $100
- COGS = $100 ✓
- Profit = $50 - $100 = -$50 ✓ (Loss, which is accurate!)
```
✓ **Correct:** We used 1 full roll from inventory, cost should be $100

## Why This Matters

### Before Fix (Wrong)
Services appeared more profitable than they actually were because COGS was calculated based on the selling unit quantity, not the actual inventory consumed.

### After Fix (Correct)
Services now show accurate profitability based on actual inventory consumption at procurement rates.

## Technical Flow

### How `calculate_line_cogs_with_conversion()` Works

```python
def calculate_line_cogs_with_conversion(item, qty, unit):
    # 1. Get cost price in the specified unit
    unit_cost = get_item_cogs_for_unit(item, unit)
    
    # 2. Multiply by quantity
    return unit_cost × qty
```

### How `get_item_cogs_for_unit()` Works

```python
def get_item_cogs_for_unit(item, selling_unit):
    cost_price = item.cost_price  # e.g., $100 per Roll
    base_unit = item.stock_unit    # e.g., Roll (procurement unit)
    
    # If units match, return as-is
    if base_unit == selling_unit:
        return cost_price  # $100 per Roll
    
    # Otherwise, convert: cost_price ÷ conversion_factor
    # e.g., $100 ÷ 50 = $2 per Foot
    return convert_price_for_unit(cost_price, base_unit, selling_unit)
```

### The Fix in Action

**Sales (Selling Unit):**
```python
unit = line.unit  # Foot (selling unit)
unit_cost = get_item_cogs_for_unit(item, Foot)  # $100 ÷ 50 = $2/Foot
cogs = $2/Foot × 10 Feet = $20
```

**Services (Procurement Unit):**
```python
unit = item.stock_unit  # Roll (procurement unit)
unit_cost = get_item_cogs_for_unit(item, Roll)  # $100/Roll (no conversion)
cogs = $100/Roll × 1 Roll = $100
```

## Summary

- **Sales:** Correctly uses selling unit because that's what the customer bought
- **Services:** Now correctly uses procurement unit because that's what we consumed from inventory
- **Result:** Accurate COGS and profit margins for both sales and services
