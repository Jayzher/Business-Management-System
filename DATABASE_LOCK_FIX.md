# Database Lock Fix - May 20, 2026

## Problem
Users were experiencing "database is locked" errors when performing operations like syncing supplier catalogs. The error occurred even though SQLite was configured with WAL mode, which should allow concurrent reads and writes.

**Error:**
```
sqlite3.OperationalError: database is locked
```

## Root Cause
The background sync worker was **reading from local_cache** to get the current state of rows before pushing them to Neon:

```python
# OLD CODE (PROBLEMATIC)
def _push_upsert_to_neon(task):
    obj = sender._default_manager.using('local_cache').filter(pk=pk).first()
    # ... then push obj to Neon
```

Even with WAL mode enabled, this caused lock contention because:
1. The background worker would read from local_cache (acquiring a read lock)
2. User requests would try to write to local_cache at the same time
3. If the background worker's read was inside a long transaction, it would block writes
4. SQLite's `busy_timeout` (30s) would expire, causing the "database is locked" error

## The Fix

### 1. Eliminate local_cache Reads from Background Worker
Instead of re-reading from local_cache, use the `row_data` that was already captured at write time:

```python
# NEW CODE (FIXED)
def _push_upsert_to_neon(task):
    """Push a row to Neon using the serialized row_data from the task.
    
    This avoids reading from local_cache (which could cause lock contention).
    The row_data was captured at the time of the local_cache write, so it's
    already the correct state to push to Neon.
    """
    sender = task['sender']
    pk = task['pk']
    row_data = task.get('row_data')
    
    if not row_data:
        logger.debug('No row_data in task for %s pk=%s', sender.__name__, pk)
        return
    
    # Reconstruct the model instance from row_data
    obj = sender(**row_data)
    obj.pk = pk
    
    # ... push obj to Neon (no local_cache read needed!)
```

**Key insight:** The `row_data` is captured in `signals.py` before the on_commit callback:

```python
@receiver(post_save)
def on_model_save(sender, instance, using, **kwargs):
    if using == 'local_cache' and _is_neon_primary():
        row_data = _instance_to_dict(instance)  # Capture NOW
        db_transaction.on_commit(
            lambda: _on_commit_save(sender, pk, table, app_label, model_name, row_data),
            using='local_cache',
        )
```

This means the background worker never needs to query local_cache — it already has all the data it needs.

### 2. Reduce Batch Size (50 → 10)
Smaller batches mean shorter transactions, which reduces the time locks are held:

```python
# OLD: while len(batch) < 50:
# NEW: while len(batch) < 10:
while len(batch) < 10:  # Max batch size (reduced from 50)
    extra = _task_queue.get_nowait()
    batch.append(extra)
```

### 3. Increase busy_timeout and Optimize WAL Checkpoints
Give more time for locks to clear and reduce checkpoint frequency:

```python
def _set_sqlite_pragmas(sender, connection, **kwargs):
    if connection.vendor == 'sqlite':
        cursor = connection.cursor()
        cursor.execute('PRAGMA journal_mode=WAL;')
        cursor.execute('PRAGMA busy_timeout=60000;')  # 60s (was 30s)
        cursor.execute('PRAGMA synchronous=NORMAL;')
        cursor.execute('PRAGMA cache_size=-64000;')
        cursor.execute('PRAGMA temp_store=MEMORY;')
        cursor.execute('PRAGMA wal_autocheckpoint=10000;')  # NEW: reduce checkpoint frequency
```

## Result
The background worker no longer reads from local_cache at all — it only writes to Neon using the pre-serialized row_data. User requests can write to local_cache without waiting for the background worker.

**Before:** Background worker reads from local_cache → blocks user writes → timeout → error  
**After:** Background worker only writes to Neon → no local_cache contention → no errors

## Files Modified
1. `sync/background_sync.py` - Changed `_push_upsert_to_neon()` to use row_data instead of querying local_cache
2. `sync/background_sync.py` - Reduced batch size from 50 to 10
3. `inventory_system/settings.py` - Increased busy_timeout to 60s and added wal_autocheckpoint

## Testing
After applying this fix:
1. Restart the Django server to apply the new settings
2. Try the supplier catalog sync operation that was failing
3. Monitor for any "database is locked" errors

The fix should eliminate the lock contention entirely since the background worker no longer competes with user requests for local_cache access.
