# Resync Inventory - Stock Adjustment Diagnostic Guide

## Issue
Stock adjustments are not being applied during inventory resync.

## Diagnostic Steps

### Step 1: Check if Adjustments Exist

Run this in Django shell:
```python
from inventory.models import StockAdjustment
from core.models import DocumentStatus

# Check total adjustments
total = StockAdjustment.objects.count()
print(f"Total adjustments: {total}")

# Check POSTED adjustments
posted = StockAdjustment.objects.filter(status=DocumentStatus.POSTED).count()
print(f"Posted adjustments: {posted}")

# Check DRAFT adjustments
draft = StockAdjustment.objects.filter(status=DocumentStatus.DRAFT).count()
print(f"Draft adjustments: {draft}")

# List all adjustments with their status
for adj in StockAdjustment.objects.all():
    print(f"Adjustment #{adj.pk}: status={adj.status}, lines={adj.lines.count()}")
```

### Step 2: Check Adjustment Lines

```python
from inventory.models import StockAdjustment, StockAdjustmentLine
from core.models import DocumentStatus

# Check adjustments with lines
for adj in StockAdjustment.objects.filter(status=DocumentStatus.POSTED):
    print(f"\nAdjustment #{adj.pk} ({adj.document_number}):")
    print(f"  Status: {adj.status}")
    print(f"  Lines: {adj.lines.count()}")
    
    for line in adj.lines.all():
        diff = line.qty_counted - line.qty_system
        print(f"    Item: {line.item.code}")
        print(f"    Location: {line.location.code}")
        print(f"    System: {line.qty_system}, Counted: {line.qty_counted}")
        print(f"    Difference: {diff}")
        print(f"    Unit: {line.unit.abbreviation}")
```

### Step 3: Run Resync with Debug Output

```bash
# Run resync in dry-run mode to see what would happen
python manage.py resync_inventory --phase 2 --dry-run

# Look for this output:
# [ADJUSTMENT] Processed X adjustment document(s) with Y line(s)
```

### Step 4: Check if Adjustments are in the Right Order

The resync command should process documents in this order:
1. GoodsReceipt
2. DeliveryNote
3. SalesPickup
4. StockTransfer
5. DamagedReport
6. POSSale
7. POSRefund
8. InventoryToSupplyTransfer
9. PurchaseReturn
10. SalesReturn
11. CustomerService
12. **StockAdjustment** (LAST)

### Step 5: Manual Balance Check

```python
from inventory.models import StockAdjustment, StockBalance
from core.models import DocumentStatus
from decimal import Decimal

# Pick a specific item and location
item_id = 1  # Replace with actual item ID
location_id = 1  # Replace with actual location ID

# Check current balance
try:
    bal = StockBalance.objects.get(item_id=item_id, location_id=location_id)
    print(f"Current balance: {bal.qty_on_hand}")
except StockBalance.DoesNotExist:
    print("No balance record exists")

# Check if there are adjustments for this item/location
adjustments = StockAdjustment.objects.filter(
    status=DocumentStatus.POSTED,
    lines__item_id=item_id,
    lines__location_id=location_id
).distinct()

print(f"\nAdjustments for this item/location: {adjustments.count()}")

for adj in adjustments:
    for line in adj.lines.filter(item_id=item_id, location_id=location_id):
        diff = line.qty_counted - line.qty_system
        print(f"  Adjustment #{adj.pk}:")
        print(f"    System: {line.qty_system}")
        print(f"    Counted: {line.qty_counted}")
        print(f"    Difference: {diff}")
        print(f"    Should {'ADD' if diff > 0 else 'SUBTRACT'} {abs(diff)}")
```

## Common Issues and Solutions

### Issue 1: Adjustments are DRAFT, not POSTED

**Symptom**: Adjustments exist but aren't being processed

**Check**:
```python
from inventory.models import StockAdjustment

for adj in StockAdjustment.objects.all():
    print(f"Adjustment #{adj.pk}: status={adj.status}")
```

**Solution**: Post the adjustments
```python
from inventory.models import StockAdjustment
from core.models import DocumentStatus

# Update all DRAFT adjustments to POSTED
StockAdjustment.objects.filter(status=DocumentStatus.DRAFT).update(
    status=DocumentStatus.POSTED
)
```

### Issue 2: Adjustment Lines Have Zero Difference

**Symptom**: Adjustments exist but qty_counted == qty_system

**Check**:
```python
from inventory.models import StockAdjustmentLine

for line in StockAdjustmentLine.objects.all():
    diff = line.qty_counted - line.qty_system
    if diff == 0:
        print(f"Line #{line.pk}: No difference (counted={line.qty_counted}, system={line.qty_system})")
```

**Solution**: These lines are correctly skipped (no adjustment needed)

### Issue 3: Unit Conversion Issues

**Symptom**: Adjustments exist but quantities don't match expected values

**Check**:
```python
from inventory.models import StockAdjustmentLine
from catalog.models import convert_to_base_unit

for line in StockAdjustmentLine.objects.all():
    item = line.item
    target_unit = item.default_unit  # or item.selling_unit if set
    
    try:
        converted = convert_to_base_unit(
            abs(line.qty_counted - line.qty_system),
            line.unit,
            target_unit,
            item=item
        )
        print(f"Item {item.code}: {line.unit.abbreviation} -> {target_unit.abbreviation} = {converted}")
    except Exception as e:
        print(f"ERROR converting item {item.code}: {e}")
```

**Solution**: Add missing unit conversions

### Issue 4: Location is NULL

**Symptom**: Adjustments exist but location_id is None

**Check**:
```python
from inventory.models import StockAdjustmentLine

null_locations = StockAdjustmentLine.objects.filter(location__isnull=True)
print(f"Lines with NULL location: {null_locations.count()}")

for line in null_locations:
    print(f"  Line #{line.pk}: item={line.item.code}, location=NULL")
```

**Solution**: Fix the data - adjustments must have a location

### Issue 5: Adjustment Not in doc_specs List

**Symptom**: Adjustments aren't being processed in Phase 1

**Check**: Look at the `_iter_expected_moves` function in resync_inventory.py

**Verify** this line exists at the END of doc_specs:
```python
('StockAdjustment', StockAdjustment.objects.filter(status=DocumentStatus.POSTED)...),
```

## Testing the Fix

### Test 1: Simple Adjustment

```python
from inventory.models import StockAdjustment, StockAdjustmentLine, StockBalance
from catalog.models import Item
from warehouses.models import Location
from core.models import DocumentStatus
from decimal import Decimal

# Get an item and location
item = Item.objects.first()
location = Location.objects.first()

# Check current balance
try:
    bal = StockBalance.objects.get(item=item, location=location)
    current_qty = bal.qty_on_hand
except StockBalance.DoesNotExist:
    current_qty = Decimal('0')

print(f"Current balance: {current_qty}")

# Create an adjustment
adj = StockAdjustment.objects.create(
    document_number='TEST-ADJ-001',
    warehouse=location.warehouse,
    status=DocumentStatus.POSTED,
    created_by_id=1,  # Replace with actual user ID
)

# Add a line that increases stock by 10
StockAdjustmentLine.objects.create(
    adjustment=adj,
    item=item,
    location=location,
    qty_system=current_qty,
    qty_counted=current_qty + Decimal('10'),
    unit=item.default_unit,
)

print(f"Created adjustment: {adj.document_number}")
print(f"  System: {current_qty}")
print(f"  Counted: {current_qty + Decimal('10')}")
print(f"  Difference: +10")

# Run resync
print("\nRun: python manage.py resync_inventory --phase 2")
print("Expected new balance: {current_qty + 10}")
```

### Test 2: Verify Order of Processing

Add this to the resync command temporarily:

```python
# In _build_balance_from_documents, add at the start:
def _build_balance_from_documents(warn_fn):
    warn_fn("  [DEBUG] Starting balance calculation...")
    
    # ... existing code ...
    
    # Before StockAdjustment section:
    warn_fn("  [DEBUG] Processing StockAdjustments (LAST STEP)...")
    adj_qs = StockAdjustment.objects.filter(status=DocumentStatus.POSTED)
    warn_fn(f"  [DEBUG] Found {adj_qs.count()} posted adjustments")
```

## Expected Output

When running `python manage.py resync_inventory --phase 2`, you should see:

```
--- Phase 2: Recalculating StockBalance ---
  Building correct balances from all posted documents...
  [ADJUSTMENT] Processed 3 adjustment document(s) with 5 line(s)
  Computed 150 (item, location) buckets.
  
  Creates: 5  Updates: 145  Unchanged: 0
  Committed: 5 created, 145 updated.
```

## If Adjustments Still Don't Apply

### Check the _accumulate function

```python
def _accumulate(bucket, item_id, location_id, delta):
    # Skip entries with no valid location or item
    if item_id is None or location_id is None:
        return
    bucket[(item_id, location_id)] += delta
```

Make sure:
1. `item_id` is not None
2. `location_id` is not None
3. `delta` is not zero

### Add More Debug Output

Modify the StockAdjustment section:

```python
for adj in adj_qs:
    warn_fn(f"  [DEBUG] Processing adjustment #{adj.pk} ({adj.document_number})")
    for line in adj.lines.all():
        raw_diff = line.qty_counted - line.qty_system
        if raw_diff == 0:
            warn_fn(f"    [DEBUG] Skipping line (no difference): item={line.item.code}")
            continue
        
        warn_fn(f"    [DEBUG] Line: item={line.item.code}, loc={line.location.code}, diff={raw_diff}")
        
        target_unit = _inventory_unit(line.item)
        q = _safe_convert(abs(raw_diff), line.unit, target_unit,
                          f"Adj#{adj.pk} item={line.item.code}", warn_fn, item=line.item)
        
        warn_fn(f"    [DEBUG] Converted qty: {q}, will {'ADD' if raw_diff > 0 else 'SUBTRACT'}")
        
        _accumulate(bal, line.item_id, line.location_id,
                    q if raw_diff > 0 else -q)
        
        warn_fn(f"    [DEBUG] Accumulated to bucket ({line.item_id}, {line.location_id})")
```

## Summary

The most common reasons adjustments don't apply:

1. ❌ **Status is DRAFT** - Must be POSTED
2. ❌ **qty_counted == qty_system** - No difference to apply
3. ❌ **location_id is NULL** - Can't accumulate without location
4. ❌ **Unit conversion fails** - Missing conversion rules
5. ❌ **Adjustment not in correct position** - Must be processed LAST

Run through the diagnostic steps above to identify which issue you're facing!
