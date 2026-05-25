# Services COGS Unit Fix

## Problem
Services COGS calculation was incorrectly using the **Selected Selling Unit** instead of the **Procurement Unit** (stock_unit/default_unit) when calculating Cost of Goods Sold.

This caused incorrect COGS calculations when:
- A service line item had a different selling unit than its procurement unit
- Unit conversions existed between the selling unit and procurement unit
- The cost price needed to be converted from the procurement unit to the selling unit

## Root Cause
The `service_invoice_cogs()` function in `core/cogs.py` was passing `line.unit` (the selling unit selected by the user) to `calculate_line_cogs_with_conversion()`, which then converted the cost price from the procurement unit to the selling unit.

**Example of the bug:**
- Item: Wire Cable
- Procurement Unit: Roll (cost_price = $100 per Roll)
- Selling Unit: Foot
- Conversion: 1 Roll = 50 Feet
- Service Line: 10 Feet @ $5/Foot (selling price)

**Before Fix (WRONG):**
- COGS per Foot = $100 / 50 = $2/Foot
- Total COGS = 10 Feet × $2/Foot = $20 ✗ (Incorrect - assumes we consumed 10 feet)

**After Fix (CORRECT):**
- Service consumes from inventory at procurement unit (Roll)
- COGS = $100 per Roll (no conversion needed)
- Total COGS = $100 ✓ (Correct - we consumed 1 roll from inventory)

## Solution
Modified the COGS calculation to use `item.stock_unit` (which returns `item.default_unit`, the procurement unit) instead of `line.unit` (the selling unit) for Services.

### Files Changed

#### 1. `core/cogs.py` - `service_invoice_cogs()` function
**Changed:**
- Product lines: Now use `line.item.stock_unit` instead of `line.unit`
- Bundle lines: Now use `pli.item.stock_unit` instead of `pli.unit`

**Rationale:** Services consume inventory at the procurement rate, not the selling rate. The selling unit is only used for customer-facing pricing, not for internal cost tracking.

#### 2. `services/views.py` - `service_detail_view()` P&L calculation
**Changed:**
- Product line P&L: Now uses `line.item.stock_unit` for COGS calculation
- Bundle P&L: Now uses `pli.item.stock_unit` for COGS calculation
- Updated import from `catalog.models.get_cost_for_unit` to `catalog.utils.get_item_cogs_for_unit`

**Rationale:** The P&L display should match the actual COGS calculation used in invoices.

## Why Sales Remains Unchanged
Sales COGS calculation correctly uses the selling unit because:
1. Sales transactions are customer-facing and priced in the selling unit
2. The selling unit represents the actual quantity sold to the customer
3. COGS should reflect the cost of the quantity sold in the unit it was sold in

## Testing Recommendations
1. Create a test item with different procurement and selling units
2. Add unit conversion between the two units
3. Create a service with this item using the selling unit
4. Complete the service and verify COGS uses the procurement unit rate
5. Compare with a sales order using the same item to verify sales still uses selling unit

## Impact
- **Services:** COGS now correctly calculated using procurement unit
- **Sales:** No change - continues to use selling unit (correct behavior)
- **Invoices:** Service invoices will now show accurate COGS and profit margins
- **P&L Reports:** Service P&L will now reflect true material costs
