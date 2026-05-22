# Why Orphaned Foreign Keys Appeared After Sync

## The Problem

After running `db_sync --direction local_to_neon`, when you tried to sync back with `db_sync --direction neon_to_local`, you got this error:

```
The row in table 'procurement_purchaseorder' with primary key '19' has an invalid 
foreign key: procurement_purchaseorder.supplier_id contains a value '10' that does 
not have a corresponding value in partners_supplier.id.
```

## Root Cause

The orphaned FKs appeared because of how the sync handles conflicts:

### 1. **`ignore_conflicts=True` in bulk_create**

In `db_sync.py` line 161-163:
```python
model.objects.using(dst).bulk_create(
    batch, batch_size=BATCH_SIZE, ignore_conflicts=True,
)
```

When syncing Local → Neon:
- If a record with the same primary key **already exists** on Neon, it's **silently skipped**
- Child records (PurchaseOrder) are inserted successfully
- But parent records (Supplier ID 10) are skipped due to conflicts
- Result: **Orphaned foreign keys**

### 2. **What Likely Happened**

**Scenario A: Partial Deletion on Neon**
1. Someone deleted Supplier ID 10 on Neon (maybe through admin panel or API)
2. The cascade delete didn't work properly, OR child records were in local DB only
3. Local DB still had PurchaseOrder referencing Supplier ID 10
4. When syncing Local → Neon, the PurchaseOrder was copied but Supplier 10 wasn't (conflict/already deleted)

**Scenario B: Concurrent Modifications**
1. Local DB had Supplier 10 and related records
2. Neon had a different version of Supplier 10 (or it was deleted)
3. During sync, Supplier 10 was skipped (conflict), but child records were inserted
4. Result: Orphaned references

**Scenario C: Failed Cascade Deletes**
1. ON DELETE CASCADE constraints weren't properly set up
2. Parent records were deleted without cleaning up children
3. Orphaned records accumulated over time

## The Orphaned Records Found

From the scan, we found **51 orphaned records** across 10 tables:

| Table | Count | Issue |
|-------|-------|-------|
| `core_supplymovement` | 7 | Missing supply_item_id=209 |
| `inventory_inventorytosupplytransferline` | 4 | Missing transfer IDs 8, 9, 10 |
| `procurement_goodsreceiptline` | 1 | Missing goods_receipt_id=156 |
| `procurement_purchaseorder` | 1 | **Missing supplier_id=10** ⚠️ |
| `procurement_suppliercatalogentry` | 4 | Missing supplier_id=10 |
| `procurement_goodsreceipt` | 1 | Missing supplier_id=10 |
| `sales_salesreturnline` | 3 | Missing sales_return_id=3 |
| `sales_deliveryline` | 10 | Missing delivery IDs 114, 122 |
| `sales_salesorderline` | 10 | Missing sales_order IDs |
| `sales_salespickupline` | 10 | Missing pickup_id=207 |

## Why This Blocks Neon → Local Sync

When syncing Neon → Local:
1. The script runs migrations on the destination (local SQLite)
2. Django's migration system **validates foreign key constraints**
3. It finds that PurchaseOrder ID 19 references Supplier ID 10
4. But Supplier ID 10 doesn't exist in the local DB
5. Migration fails with FK constraint violation

## The Solution

### Option 1: Use the Built-in Django Command (Recommended)

```bash
# Preview what will be deleted (dry-run)
python manage.py cleanup_orphaned_fks --dry-run

# Clean up all orphaned FKs
python manage.py cleanup_orphaned_fks

# Then retry the sync
python manage.py db_sync --direction neon_to_local
```

### Option 2: Use the Custom Script

```bash
# Run the interactive fixer
python fix_orphaned_fks.py

# Choose option 1 to fix automatically
# Then confirm with 'yes'
```

### Option 3: Manual SQL (Advanced)

```bash
# Set DATABASE_URL to use local SQLite
set DATABASE_URL=sqlite

# Run Django shell
python manage.py shell

# Execute cleanup queries manually
from django.db import connection
cursor = connection.cursor()

# Delete orphaned purchase order
cursor.execute("DELETE FROM procurement_purchaseorder WHERE supplier_id = 10")

# Delete other orphaned records...
```

## Prevention

To prevent this in the future:

### 1. **Fix the sync script to handle conflicts better**

Instead of `ignore_conflicts=True`, use `update_conflicts` or handle conflicts explicitly:

```python
# Option A: Update on conflict
model.objects.using(dst).bulk_create(
    batch, 
    batch_size=BATCH_SIZE, 
    update_conflicts=True,
    update_fields=['field1', 'field2', ...]  # specify fields to update
)

# Option B: Delete and recreate
model.objects.using(dst).all().delete()
model.objects.using(dst).bulk_create(batch, batch_size=BATCH_SIZE)
```

### 2. **Add pre-sync validation**

Before syncing, validate FK integrity on the source database.

### 3. **Ensure proper CASCADE deletes**

Make sure all FK relationships have proper `on_delete` behavior:
```python
supplier = models.ForeignKey(
    Supplier, 
    on_delete=models.CASCADE  # or PROTECT to prevent deletion
)
```

### 4. **Run cleanup before sync**

Always clean up orphaned FKs before syncing:
```bash
python manage.py cleanup_orphaned_fks
python manage.py db_sync --direction local_to_neon
```

## Summary

The orphaned FKs appeared because:
1. ✗ `ignore_conflicts=True` silently skips parent records during sync
2. ✗ Child records are inserted without their parents
3. ✗ No validation happens until the reverse sync tries to run migrations

**Fix it now:**
```bash
python manage.py cleanup_orphaned_fks
python manage.py db_sync --direction neon_to_local
```
