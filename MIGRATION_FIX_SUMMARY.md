# Migration Fix Summary

## Issue
The `cashflow_monthlycashflowsummary` table was not being created in either SQLite or Neon PostgreSQL databases, even though migration `0003_monthlycashflowsummary` showed as applied. This caused the background Neon→SQLite sync to fail with:
```
Background Neon→SQLite sync failed: no such table: cashflow_monthlycashflowsummary
```

## Root Cause
The migration `cashflow/migrations/0003_monthlycashflowsummary.py` was marked as applied (faked) in both databases but the actual table creation SQL was never executed. This happens when:
1. Migrations are faked during development/testing
2. Database schema gets out of sync with migration history
3. Tables are manually dropped but migrations aren't rolled back

## Solution Applied

### 1. Fixed SQLite Database
```bash
# Applied the missing migration
python manage.py migrate cashflow

# Verified table exists
python manage.py shell -c "from django.db import connection; cursor = connection.cursor(); cursor.execute('SELECT name FROM sqlite_master WHERE type=\'table\' AND name=\'cashflow_monthlycashflowsummary\''); print('Table exists:', bool(cursor.fetchone()))"
# Output: Table exists: True
```

### 2. Fixed Neon PostgreSQL Database
```bash
# Faked migration back to 0002
python -c "import os; os.environ['DATABASE_URL'] = 'postgresql://...'; os.environ['DJANGO_SETTINGS_MODULE'] = 'inventory_system.settings'; import django; django.setup(); from django.core.management import call_command; call_command('migrate', 'cashflow', '0002', '--fake')"

# Reapplied migration 0003 (actually creates the table this time)
python -c "import os; os.environ['DATABASE_URL'] = 'postgresql://...'; os.environ['DJANGO_SETTINGS_MODULE'] = 'inventory_system.settings'; import django; django.setup(); from django.core.management import call_command; call_command('migrate', 'cashflow')"

# Verified table exists
python -c "import os; os.environ['DATABASE_URL'] = 'postgresql://...'; os.environ['DJANGO_SETTINGS_MODULE'] = 'inventory_system.settings'; import django; django.setup(); from django.db import connection; cursor = connection.cursor(); cursor.execute('SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_schema = \'public\' AND table_name = \'cashflow_monthlycashflowsummary\')'); print('Table exists in Neon:', cursor.fetchone()[0])"
# Output: Table exists in Neon: True
```

### 3. Cleaned Up Orphaned Foreign Keys
```bash
# Cleaned 149 orphaned FK references from SQLite
python manage.py cleanup_orphaned_fks
```

## Verification
After the fixes, the background sync now works successfully:
```
============================================================
DB Sync: Neon PostgreSQL  -->  Local SQLite
============================================================
...
Sync complete! 14140 total rows copied.
No errors!
============================================================
```

## Enhanced db_sync.py
The `db_sync.py` command was already enhanced with:
- Pre-sync migration checks on both source and destination
- Automatic orphaned FK cleanup before sync
- Post-sync FK integrity validation
- Defensive table existence checks before truncation

## Remaining Orphaned FKs
The 152 orphaned FKs detected after sync exist in the Neon database itself (not created during sync). These are historical data integrity issues that should be cleaned up in Neon:
- Missing catalog items (deleted items still referenced)
- Missing sales orders (deleted orders still referenced)
- Missing delivery notes (deleted deliveries still referenced)
- Missing sales pickups (deleted pickups still referenced)

To clean these up in Neon, run the cleanup command against Neon database.

## Status
✅ **RESOLVED** - Both databases now have the `cashflow_monthlycashflowsummary` table and background sync works without errors.
