# Supplier Catalog Cost Price Update

## Overview

The Supplier Catalog Sync functionality automatically updates Item Cost Prices based on supplier catalog data. This ensures that inventory valuation and COGS calculations use the most conservative (highest) cost across all suppliers.

## How It Works

### 1. Sync Process

There are two sync methods available:

#### A. Sync from Purchase Orders (`supplier_catalog_sync_view`)
- Scans all **APPROVED** and **POSTED** Purchase Orders
- Imports supplier prices into `SupplierCatalogEntry` records
- Uses the latest PO price for each supplier + item + unit combination

#### B. Sync from Goods Receipts (`supplier_catalog_sync_grn_view`)
- Scans all **POSTED** Goods Receipts linked to Purchase Orders
- Imports supplier prices based on actual receipt dates
- Only updates if the GRN receipt date is newer than existing entries

### 2. Automatic Cost Price Update

After syncing supplier catalog entries, the system automatically calls `_update_item_cost_from_supplier_catalog()` which:

1. **Collects all supplier prices** for each item from `SupplierCatalogEntry`
2. **Handles unit conversions** - converts prices to the item's default unit for comparison
3. **Selects the HIGHEST price** across all suppliers
4. **Updates `Item.cost_price`** with the highest price
5. **Syncs changes** to the changelog and local cache

### 3. Why Use the Highest Price?

The system uses the **highest** supplier price (not the lowest or average) for these reasons:

- **Conservative COGS**: Never understates the cost of goods sold
- **Accurate Inventory Valuation**: Ensures inventory is valued at the maximum cost
- **Profit Margin Safety**: Prevents overestimating profit margins
- **Multi-supplier Protection**: Accounts for price variations across suppliers

## Implementation Details

### Key Function: `_update_item_cost_from_supplier_catalog()`

Located in: `procurement/views.py` (line 507)

**Parameters:**
- `item_ids` (optional): List of Item IDs to update. If None, updates all items with catalog entries.

**Returns:**
```python
{
    'updated_count': int,      # Items whose cost_price changed
    'unchanged_count': int,    # Items whose cost_price was already correct
    'skipped_count': int       # Items that couldn't be priced (no valid entries)
}
```

**Logic:**
1. Fetches all `SupplierCatalogEntry` records for specified items
2. Groups entries by item
3. For each item:
   - Converts all supplier prices to the item's default unit
   - Finds the maximum price
   - Updates `Item.cost_price` if different
4. Triggers sync signals for updated items

### Unit Conversion Handling

The function properly handles cross-unit pricing:
- Only accepts conversions when a real `UnitConversion` record exists
- Uses `convert_price_for_unit()` for accurate price conversion
- Skips entries that can't be converted to the base unit

### Database Updates

- Uses `QuerySet.update()` for efficiency
- Explicitly calls `bulk_sync_upsert()` to trigger sync signals
- Tracks updated PKs for changelog synchronization

## User Interface

### Templates Updated

1. **`supplier_catalog_sync.html`** - PO sync page
2. **`supplier_catalog_sync_grn.html`** - GRN sync page

Both templates now clearly inform users that:
- Cost prices will be automatically updated after sync
- The highest price across all suppliers will be used
- This ensures conservative COGS and inventory valuation

### Success Messages

After syncing, users see detailed statistics:
```
Sync complete: X new entries created, Y entries updated from past PO data.
Item costs updated: Z (unchanged: A, skipped: B).
```

## Usage

### Via Web Interface

1. Navigate to **Procurement → Supplier Catalog**
2. Click **"Sync from POs"** or **"Sync from GRNs"**
3. Review the statistics (eligible POs/GRNs, line counts)
4. Click **"Start Sync"**
5. System will:
   - Import/update supplier catalog entries
   - Automatically update item cost prices
   - Display success message with statistics

### Programmatic Usage

```python
from procurement.views import _update_item_cost_from_supplier_catalog

# Update all items
stats = _update_item_cost_from_supplier_catalog()

# Update specific items
item_ids = [1, 2, 3, 4, 5]
stats = _update_item_cost_from_supplier_catalog(item_ids=item_ids)

print(f"Updated: {stats['updated_count']}")
print(f"Unchanged: {stats['unchanged_count']}")
print(f"Skipped: {stats['skipped_count']}")
```

## Edge Cases Handled

1. **Zero or negative prices**: Ignored during calculation
2. **Missing unit conversions**: Entries skipped if conversion not found
3. **No valid prices**: Item skipped, cost_price unchanged
4. **Same price**: Counted as "unchanged", no database update
5. **Multiple suppliers**: All prices compared, highest selected

## Related Files

- `procurement/models.py` - `SupplierCatalogEntry` model
- `procurement/views.py` - Sync views and helper function
- `catalog/models.py` - `Item` model with `cost_price` field
- `catalog/utils.py` - Unit conversion utilities
- `templates/procurement/supplier_catalog_sync.html`
- `templates/procurement/supplier_catalog_sync_grn.html`

## Testing

To verify the functionality:

1. Create multiple `SupplierCatalogEntry` records for the same item with different prices
2. Run the sync process
3. Check that `Item.cost_price` equals the highest supplier price
4. Verify unit conversions are handled correctly for cross-unit entries

## Future Enhancements

Possible improvements:
- Option to use average price instead of highest
- Option to use lowest price for specific items
- Weighted average based on purchase frequency
- Price history tracking and trend analysis
- Alerts when cost prices change significantly
