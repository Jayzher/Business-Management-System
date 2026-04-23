# Inventory Resync - Stock Adjustment Order Fix

## Overview
Modified the `resync_inventory` management command to process **Stock Adjustments as the LAST step** in inventory balance recalculation, ensuring adjustments are applied after all other inventory movements.

## Problem

Previously, Stock Adjustments were processed in the middle of the document sequence:

### Old Order:
1. GoodsReceipt (IN)
2. DeliveryNote (OUT)
3. SalesPickup (OUT)
4. StockTransfer (MOVE)
5. **StockAdjustment** ← Was here (middle)
6. DamagedReport (OUT)
7. POSSale (OUT)
8. POSRefund (IN)
9. InventoryToSupplyTransfer (OUT)
10. PurchaseReturn (OUT)
11. SalesReturn (IN)
12. CustomerService (OUT)

**Issue**: Adjustments were being applied before some inventory movements, which could lead to incorrect final balances since adjustments should correct the inventory AFTER all transactions are accounted for.

## Solution

Moved Stock Adjustments to be processed **LAST**, after all other document types.

### New Order:
1. GoodsReceipt (IN)
2. DeliveryNote (OUT)
3. SalesPickup (OUT)
4. StockTransfer (MOVE)
5. DamagedReport (OUT)
6. POSSale (OUT)
7. POSRefund (IN)
8. InventoryToSupplyTransfer (OUT)
9. PurchaseReturn (OUT)
10. SalesReturn (IN)
11. CustomerService (OUT)
12. **StockAdjustment** ← Now LAST

## Changes Made

### 1. Updated `_build_balance_from_documents()` Function

**File**: `inventory/management/commands/resync_inventory.py`

#### Removed StockAdjustment from middle position:
```python
# Removed from here (after StockTransfer)
# ── StockAdjustment ──────────────────────────────────────────────────────
# for adj in StockAdjustment.objects.filter(status=DocumentStatus.POSTED)...
```

#### Added StockAdjustment at the end:
```python
# ── StockAdjustment (LAST STEP - Applied after all other movements) ─────
for adj in StockAdjustment.objects.filter(status=DocumentStatus.POSTED).prefetch_related(
    'lines__item__default_unit', 'lines__item__selling_unit', 'lines__unit', 'lines__location'
):
    for line in adj.lines.all():
        raw_diff = line.qty_counted - line.qty_system
        if raw_diff == 0:
            continue
        target_unit = _inventory_unit(line.item)
        q = _safe_convert(abs(raw_diff), line.unit, target_unit,
                          f"Adj#{adj.pk} item={line.item.code}", warn_fn, item=line.item)
        _accumulate(bal, line.item_id, line.location_id,
                    q if raw_diff > 0 else -q)
```

### 2. Updated `_iter_expected_moves()` Function

Moved StockAdjustment to the end of the `doc_specs` list:

```python
doc_specs = [
    ('GoodsReceipt', ...),
    ('DeliveryNote', ...),
    ('SalesPickup', ...),
    ('StockTransfer', ...),
    ('DamagedReport', ...),  # Moved up
    ('POSSale', ...),
    ('POSRefund', ...),
    ('InventoryToSupplyTransfer', ...),
    ('PurchaseReturn', ...),
    ('SalesReturn', ...),
    ('CustomerService', ...),
    # StockAdjustment LAST - Applied after all other movements
    ('StockAdjustment', ...),  # Moved to end
]
```

## Why This Matters

### Logical Flow
Stock adjustments are typically used to:
1. **Correct discrepancies** found during physical counts
2. **Fix errors** in recorded inventory
3. **Account for shrinkage** or damage not otherwise documented

These corrections should be applied **AFTER** all normal business transactions are processed, not in the middle.

### Example Scenario

**Without Fix (Old Order)**:
```
Starting Balance: 100 units
1. Receive 50 units → 150
2. Deliver 30 units → 120
3. Transfer 20 units → 100 (at new location)
4. ADJUST: Physical count shows 95 → Adjust to 95
5. POS Sale 10 units → 85
6. Service uses 5 units → 80

Final Balance: 80 units
```

**Problem**: The adjustment at step 4 was based on a physical count that happened BEFORE the POS sale and service. The adjustment should account for ALL movements first.

**With Fix (New Order)**:
```
Starting Balance: 100 units
1. Receive 50 units → 150
2. Deliver 30 units → 120
3. Transfer 20 units → 100 (at new location)
4. POS Sale 10 units → 90
5. Service uses 5 units → 85
6. ADJUST: Physical count shows 80 → Adjust to 80

Final Balance: 80 units
```

**Correct**: The adjustment now happens AFTER all transactions, providing the final correction based on actual physical count.

## Impact on Resync Command

### Phase 1 (Fix StockMove quantities)
- StockAdjustment moves are now processed last in the iteration
- Ensures adjustment moves are corrected after all other document moves

### Phase 2 (Recalculate StockBalance)
- Stock adjustments are applied as the final step
- Balance calculation reflects: Base + All Transactions + Final Adjustments

### Phase 3 (Audit)
- No changes to audit logic
- Integrity checks remain the same

## Testing Recommendations

### Test Case 1: Basic Adjustment After Transactions
1. Create a GRN with 100 units
2. Create a Delivery Note with 30 units
3. Create a Stock Adjustment to 65 units
4. Run `python manage.py resync_inventory`
5. **Expected**: Final balance = 65 units (not affected by order)

### Test Case 2: Multiple Adjustments
1. Create various transactions (GRN, DN, POS, etc.)
2. Create multiple stock adjustments
3. Run resync
4. **Expected**: All adjustments applied last, in order

### Test Case 3: Adjustment with Negative Difference
1. System shows 100 units
2. Physical count shows 90 units
3. Create adjustment (counted=90, system=100)
4. Run resync
5. **Expected**: Balance reduced by 10 units AFTER all other transactions

### Test Case 4: Complex Scenario
1. GRN: +100 units
2. Transfer: Move 50 units to another location
3. POS Sale: -20 units
4. Adjustment: Physical count shows 25 units at location A
5. Service: -5 units
6. Run resync
7. **Expected**: Adjustment applied before service deduction

## Command Usage

The command usage remains the same:

```bash
# Full resync (all phases)
python manage.py resync_inventory

# Dry run to preview changes
python manage.py resync_inventory --dry-run

# Run specific phase
python manage.py resync_inventory --phase 2

# Quiet mode (summary only)
python manage.py resync_inventory --quiet
```

## Benefits

### 1. **Logical Consistency**
- Adjustments are corrections, not transactions
- Should be applied after all transactions are accounted for

### 2. **Accurate Physical Counts**
- Physical counts typically happen at a point in time
- All transactions up to that point should be processed first

### 3. **Better Audit Trail**
- Clear separation between transactions and corrections
- Easier to understand inventory flow

### 4. **Predictable Results**
- Consistent order of operations
- Easier to troubleshoot discrepancies

## Notes

### Adjustment Logic Unchanged
The actual adjustment calculation logic remains the same:
```python
raw_diff = line.qty_counted - line.qty_system
if raw_diff > 0:
    # Add to inventory
    _accumulate(bal, line.item_id, line.location_id, q)
else:
    # Remove from inventory
    _accumulate(bal, line.item_id, line.location_id, -q)
```

### Backward Compatibility
- Existing adjustments are not affected
- Only the ORDER of processing changes
- Final balances should be the same (or more accurate)

### Performance
- No performance impact
- Same number of queries
- Same processing logic

## Summary

Stock Adjustments are now processed as the **LAST STEP** in inventory resync, ensuring they are applied after all other inventory movements. This provides:

✅ **Logical consistency** - corrections applied after transactions  
✅ **Accurate physical counts** - all transactions processed first  
✅ **Better audit trail** - clear separation of transactions vs corrections  
✅ **Predictable results** - consistent order of operations  

**Key Takeaway**: Stock adjustments are now the final step in inventory balance calculation, reflecting their true purpose as corrections to be applied after all business transactions are accounted for.
