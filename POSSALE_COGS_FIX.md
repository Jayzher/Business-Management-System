# POSSale COGS Calculation Fix

## Issue
Multiple files were trying to access `grand_total_cogs` attribute on `POSSale` objects, which doesn't exist:
```
AttributeError: 'POSSale' object has no attribute 'grand_total_cogs'
```

This error occurred in:
1. `/cashflow/` page - `cashflow/views.py` line 115
2. Monthly signals - `cashflow/monthly_signals.py` line 45
3. Management command - `cashflow/management/commands/calculate_monthly_cashflow.py` line 234

## Root Cause
The `POSSale` model doesn't have a `grand_total_cogs` field like the `Invoice` model does. COGS for POS sales must be calculated dynamically from the sale lines using the `pos_sale_cogs()` function from `core.cogs`.

## Solution Applied

### 1. Fixed `cashflow/monthly_signals.py`
Changed POS sales COGS calculation to use dynamic calculation:
```python
from core.cogs import pos_sale_cogs

pos_sales = POSSale.objects.filter(
    status=SaleStatus.POSTED,
    created_at__gte=start_date,
    created_at__lt=end_date,
).prefetch_related('lines__item', 'lines__unit', 'bundle_lines__price_list__items')

for sale in pos_sales:
    revenue = sale.grand_total or Decimal('0')
    cogs = pos_sale_cogs(sale)  # Calculate COGS dynamically
    gross_profit = revenue - cogs
    capital_sales += gross_profit
```

### 2. Fixed `cashflow/views.py`
Updated the `transaction_list` view to calculate COGS dynamically for POS sales:
```python
from core.cogs import pos_sale_cogs

for sale in pos_sales:
    revenue = sale.grand_total or Decimal('0')
    cogs = pos_sale_cogs(sale)  # Calculate COGS dynamically
    gross_profit = revenue - cogs
    sales_breakdown.append({
        'type': 'POS Sale',
        'number': sale.sale_no,
        'date': sale.created_at,
        'revenue': revenue,
        'cogs': cogs,
        'gross_profit': gross_profit,
    })
```

### 3. Fixed `cashflow/management/commands/calculate_monthly_cashflow.py`
Updated the `_calculate_sales_gross_profit` method:
```python
from core.cogs import pos_sale_cogs

pos_sales = POSSale.objects.filter(
    status=SaleStatus.POSTED,
    created_at__gte=start_date,
    created_at__lt=end_date,
).prefetch_related('lines__item', 'lines__unit', 'bundle_lines__price_list__items')

for sale in pos_sales:
    revenue = sale.grand_total or Decimal('0')
    cogs = pos_sale_cogs(sale)
    gross_profit = revenue - cogs
    total += gross_profit
```

### How `pos_sale_cogs()` Works
The function from `core/cogs.py` calculates COGS by:
1. Iterating through regular sale lines: `item.cost_price × qty` (with unit conversion)
2. Iterating through bundle lines: sum of each bundle item's COGS × qty_sets
3. Using `calculate_line_cogs_with_conversion()` to handle unit conversions properly

## Verification
All three files now use the same approach:
- Import `pos_sale_cogs` from `core.cogs`
- Add `prefetch_related` for performance optimization
- Calculate COGS dynamically instead of accessing non-existent field
- Keep Invoice COGS calculation unchanged (uses stored `grand_total_cogs` field)

## Key Differences: POSSale vs Invoice

| Feature | POSSale | Invoice |
|---------|---------|---------|
| COGS Storage | ❌ No field | ✅ `grand_total_cogs` field |
| COGS Calculation | Dynamic via `pos_sale_cogs()` | Stored, synced via `sync_invoice_cogs` command |
| Performance | Calculated on-demand | Pre-calculated and cached |
| Use Case | Direct POS transactions | Linked to source documents (SO, POS, Service) |

## Files Modified
- ✅ `Business-Management-System/cashflow/monthly_signals.py` - Fixed COGS calculation
- ✅ `Business-Management-System/cashflow/views.py` - Fixed transaction_list view
- ✅ `Business-Management-System/cashflow/management/commands/calculate_monthly_cashflow.py` - Fixed management command

## Related Files
- `Business-Management-System/core/cogs.py` - COGS calculation functions
- `Business-Management-System/pos/models.py` - POSSale model (no COGS field)
- `Business-Management-System/core/models.py` - Invoice model (has COGS field)

## Status
✅ **RESOLVED** - All cashflow-related code now correctly calculates gross profit for POS sales using dynamic COGS calculation. The `/cashflow/` page should now load without errors.
