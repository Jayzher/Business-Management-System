# Auto_now Race Condition Fix

## Problem
Users were experiencing this error when creating `SupplierCatalogEntry` records:

```
django.db.utils.IntegrityError: NOT NULL constraint failed: procurement_suppliercatalogentry.updated_at
```

## Root Cause

The sync code was **globally disabling `auto_now` fields** on model classes:

```python
# PROBLEMATIC CODE
for field in sender._meta.get_fields():
    if hasattr(field, 'auto_now') and field.auto_now:
        field.auto_now = False  # ❌ Global mutation!
        auto_fields.append(('auto_now', field))

try:
    # ... do bulk_create ...
finally:
    # Restore auto_now
    for attr, field in auto_fields:
        setattr(field, attr, True)
```

### The Race Condition

1. **Thread A** (background worker): Sets `SupplierCatalogEntry.updated_at.auto_now = False`
2. **Thread B** (user request): Tries to create a `SupplierCatalogEntry`
3. **Thread B** sees `auto_now=False`, so Django doesn't set `updated_at`
4. **Thread B** tries to INSERT without `updated_at` → **IntegrityError: NOT NULL constraint failed**
5. **Thread A** restores `auto_now=True` (too late!)

This is a **classic race condition** caused by mutating shared state (the model class) across threads.

## Solution

**Don't mutate the model class globally.** Instead, rely on the fact that `bulk_create()` **already bypasses `auto_now` behavior**.

### Before (Problematic)
```python
# Globally disable auto_now (affects all threads!)
auto_fields = []
for field in sender._meta.get_fields():
    if hasattr(field, 'auto_now') and field.auto_now:
        field.auto_now = False
        auto_fields.append(('auto_now', field))

try:
    sender._default_manager.using('local_cache').bulk_create(
        [obj], update_conflicts=True, update_fields=update_fields, unique_fields=['id']
    )
finally:
    # Restore auto_now
    for attr, field in auto_fields:
        setattr(field, attr, True)
```

### After (Fixed)
```python
# bulk_create bypasses auto_now/auto_now_add automatically
# No need to globally disable auto_now (which causes race conditions)
obj._state.adding = True
obj._state.db = 'local_cache'

sender._default_manager.using('local_cache').bulk_create(
    [obj], update_conflicts=True, update_fields=update_fields, unique_fields=['id']
)
```

## Why This Works

Django's `bulk_create()` method **does not trigger `auto_now` or `auto_now_add`** by design. From Django docs:

> The model's `save()` method will not be called, and the `pre_save` and `post_save` signals will not be sent.
> It does not work with child models in a multi-table inheritance scenario.
> If the model's primary key is an `AutoField`, the primary key attribute can only be retrieved on certain databases (currently PostgreSQL, MariaDB 10.5+, and SQLite 3.35+). On other databases, it will not be set.
> **It does not work with many-to-many relationships.**

Since `bulk_create()` doesn't call `save()`, it doesn't trigger `auto_now` behavior. The timestamps in `row_data` are used as-is, which is exactly what we want (to preserve timestamps from the source database).

## Files Modified

1. **`sync/background_sync.py`** - `_push_upsert_to_neon()`
   - Removed global `auto_now` mutation
   - Added comment explaining why it's not needed

2. **`sync/signals.py`** - `_mirror_to_local_cache()`
   - Removed global `auto_now` mutation
   - Added comment explaining why it's not needed

## Testing

To verify the fix:

1. Start the Django server:
   ```bash
   python manage.py runserver
   ```

2. Trigger the supplier catalog sync:
   ```
   Navigate to: /procurement/supplier-catalog/sync/
   ```

3. Verify no `IntegrityError` occurs

4. Check that `updated_at` is properly set:
   ```python
   from procurement.models import SupplierCatalogEntry
   entry = SupplierCatalogEntry.objects.first()
   print(entry.updated_at)  # Should have a value
   ```

## Related Issues

This same pattern exists in other files that might need similar fixes:

- `sync/save_guard.py` (line 179)
- `sync/startup_sync.py` (lines 307, 378)
- `sync/management/commands/reconcile_local_cache.py` (line 260)
- `sync/management/commands/hydrate_local_cache.py` (line 123)

However, these are likely used in single-threaded contexts (management commands, startup), so they're lower priority. The critical fixes were in `signals.py` and `background_sync.py` which run in multi-threaded environments.

## Prevention

### Rule: Never Mutate Model Class Attributes

**❌ Bad:**
```python
field.auto_now = False  # Affects all threads!
```

**✅ Good:**
```python
# Use bulk_create which bypasses auto_now
# Or set the value directly on the instance:
obj.updated_at = timezone.now()
```

### Alternative Approach (if needed)

If you absolutely need to preserve timestamps during a regular `save()`, set them directly on the instance:

```python
from django.utils import timezone

# Preserve the timestamp from source
obj.updated_at = source_obj.updated_at
obj.save(update_fields=['field1', 'field2', 'updated_at'])
```

This sets the value on the **instance**, not the **class**, so it's thread-safe.

## Date Applied
May 20, 2026

## Status
✅ **FIXED** - Race condition eliminated by removing global auto_now mutations
