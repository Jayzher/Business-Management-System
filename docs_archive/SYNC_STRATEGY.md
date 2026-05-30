# Database Sync Strategy V2

## Problem Statement

The original sync had these issues:
1. **`ignore_conflicts=True`** silently skipped records, creating orphaned FKs
2. **No conflict resolution** - couldn't handle concurrent changes
3. **No priority system** - both databases treated equally
4. **Orphaned FKs** accumulated over time

## Solution: Priority-Based Sync with Conflict Resolution

### Core Principles

1. **Neon PostgreSQL = Source of Truth (Priority 1)**
   - Production database
   - Always wins in conflicts
   - Synced to local first

2. **Local SQLite = Fast Cache (Priority 2)**
   - Read-only cache for UI
   - New local changes synced to Neon
   - Neon changes overwrite local

3. **FK Integrity First**
   - Clean orphaned FKs before sync
   - Validate FK integrity after sync
   - Never break parent-child relationships

### Sync Modes

#### 1. MERGE Mode (Recommended)

**Smart conflict resolution with timestamp comparison**

```bash
python manage.py db_sync_v2 --direction bidirectional --mode merge --cleanup-orphans
```

**How it works:**
- For each record:
  - If PK exists in both: Compare `updated_at` timestamps
    - Source newer → Update destination
    - Destination newer → Skip (keep destination)
    - No timestamp → Skip (keep destination)
  - If PK only in source → Insert to destination
  - If PK only in destination → Keep (don't delete)

**When to use:**
- Daily syncs
- Multiple users making changes
- Want to preserve both local and remote changes

**Pros:**
- ✓ No data loss
- ✓ Handles concurrent edits
- ✓ Preserves FK integrity

**Cons:**
- ✗ Slower than FORCE mode
- ✗ Requires timestamp fields

#### 2. FORCE Mode

**Complete overwrite - truncate destination and copy everything**

```bash
python manage.py db_sync_v2 --direction neon_to_local --mode force
```

**How it works:**
- Truncate all destination tables
- Copy all source records
- Overwrite everything

**When to use:**
- Initial setup
- After major schema changes
- When destination is corrupted
- When you want a clean slate

**Pros:**
- ✓ Fast
- ✓ Simple
- ✓ Guaranteed consistency

**Cons:**
- ✗ Loses destination-only changes
- ✗ Destructive

### Sync Directions

#### 1. Bidirectional (Recommended for Production)

```bash
python manage.py db_sync_v2 --direction bidirectional --mode merge --cleanup-orphans
```

**Process:**
1. **Phase 1: Neon → Local** (Neon is source of truth)
   - Sync all Neon changes to Local
   - Neon changes overwrite Local conflicts
   
2. **Phase 2: Local → Neon** (New local changes)
   - Sync new Local records to Neon
   - Use MERGE mode (never overwrite Neon)

**When to use:**
- Production environment
- Multiple devices/users
- Want both databases in sync

#### 2. Neon → Local

```bash
python manage.py db_sync_v2 --direction neon_to_local --mode merge
```

**When to use:**
- Refresh local cache from production
- After making changes on Neon
- Initial local setup

#### 3. Local → Neon

```bash
python manage.py db_sync_v2 --direction local_to_neon --mode merge
```

**When to use:**
- Push local changes to production
- After offline work
- Backup local data

**⚠️ Warning:** Always use MERGE mode for Local → Neon to avoid overwriting production data!

### Orphaned FK Cleanup

**Automatic cleanup:**
```bash
python manage.py db_sync_v2 --direction bidirectional --mode merge --cleanup-orphans
```

**Manual cleanup:**
```bash
# Clean local SQLite
set DATABASE_URL=sqlite
python manage.py cleanup_orphaned_fks

# Clean Neon PostgreSQL (requires connection)
python manage.py cleanup_orphaned_fks --database neon
```

### Recommended Workflows

#### Daily Production Sync

```bash
# 1. Clean up orphaned FKs on both databases
python manage.py db_sync_v2 --direction bidirectional --mode merge --cleanup-orphans

# 2. Verify FK integrity
set DATABASE_URL=sqlite
python manage.py cleanup_orphaned_fks --dry-run
```

#### Initial Setup (New Device)

```bash
# Force sync from Neon to Local (clean slate)
python manage.py db_sync_v2 --direction neon_to_local --mode force
```

#### After Offline Work

```bash
# Merge local changes to Neon
python manage.py db_sync_v2 --direction local_to_neon --mode merge --cleanup-orphans
```

#### After Schema Migration

```bash
# Force sync to ensure schema consistency
python manage.py db_sync_v2 --direction neon_to_local --mode force
```

### Conflict Resolution Examples

#### Example 1: Concurrent Edit

**Scenario:**
- User A edits Supplier #10 on Neon at 10:00 AM
- User B edits Supplier #10 on Local at 10:05 AM
- Sync runs at 10:10 AM

**MERGE mode result:**
- Phase 1 (Neon → Local): User A's changes (10:00) vs User B's (10:05)
  - User B's changes are newer → Skip (keep Local)
- Phase 2 (Local → Neon): User B's changes (10:05) vs User A's (10:00)
  - User B's changes are newer → Update Neon

**Final:** User B's changes win (newer timestamp)

#### Example 2: Deletion with Children

**Scenario:**
- Supplier #10 has 5 Purchase Orders
- User deletes Supplier #10 on Neon
- Sync runs

**MERGE mode result:**
- Supplier #10 deletion detected
- Check for child records (Purchase Orders)
- **Orphaned FKs found!**
- Cleanup runs:
  - Option A: Delete child Purchase Orders (CASCADE)
  - Option B: Prevent deletion (PROTECT)
  - Option C: Set FK to NULL (SET_NULL)

**Recommendation:** Always use CASCADE deletes in models:
```python
supplier = models.ForeignKey(
    Supplier,
    on_delete=models.CASCADE  # Delete children when parent is deleted
)
```

#### Example 3: New Record on Both

**Scenario:**
- User A creates Item #500 on Neon
- User B creates Item #500 on Local (same PK!)
- Sync runs

**MERGE mode result:**
- PK conflict detected
- Compare timestamps
- Newer record wins
- Older record is overwritten

**Prevention:** Use auto-increment PKs or UUIDs to avoid PK conflicts

### Monitoring & Validation

#### Check for Orphaned FKs

```bash
# Dry run - preview only
set DATABASE_URL=sqlite
python manage.py cleanup_orphaned_fks --dry-run

# Check specific table
python manage.py cleanup_orphaned_fks --table procurement_purchaseorder --dry-run
```

#### Validate Sync Results

```bash
# Compare row counts
python manage.py db_sync_v2 --direction bidirectional --mode merge --dry-run
```

#### Check FK Integrity

```bash
# After sync, check for orphans
python manage.py db_sync_v2 --direction neon_to_local --mode merge
# Output will show: "✓ FK integrity OK" or "⚠ Found X orphaned FK(s)"
```

### Troubleshooting

#### Issue: "FK constraint failed"

**Cause:** Trying to delete a parent record with children

**Solution:**
```bash
# Clean up orphaned FKs first
python manage.py db_sync_v2 --direction bidirectional --mode merge --cleanup-orphans
```

#### Issue: "Orphaned FKs found after sync"

**Cause:** Source database has orphaned FKs

**Solution:**
```bash
# Clean source database
python manage.py cleanup_orphaned_fks

# Then re-sync
python manage.py db_sync_v2 --direction neon_to_local --mode force
```

#### Issue: "Conflict: both databases have different versions"

**Cause:** Concurrent edits without timestamps

**Solution:**
1. Add `updated_at` field to models:
```python
class MyModel(models.Model):
    updated_at = models.DateTimeField(auto_now=True)
```

2. Run migrations on both databases

3. Use MERGE mode

#### Issue: "Sync is too slow"

**Cause:** MERGE mode compares every record

**Solution:**
- Use FORCE mode for initial sync
- Use MERGE mode only for incremental syncs
- Add indexes on timestamp fields
- Increase BATCH_SIZE in db_sync_v2.py

### Best Practices

1. **Always clean orphaned FKs before sync**
   ```bash
   --cleanup-orphans
   ```

2. **Use MERGE mode for production**
   ```bash
   --mode merge
   ```

3. **Use bidirectional sync daily**
   ```bash
   --direction bidirectional
   ```

4. **Add timestamps to all models**
   ```python
   updated_at = models.DateTimeField(auto_now=True)
   ```

5. **Use CASCADE deletes**
   ```python
   on_delete=models.CASCADE
   ```

6. **Monitor FK integrity**
   ```bash
   python manage.py cleanup_orphaned_fks --dry-run
   ```

7. **Test sync with --dry-run first**
   ```bash
   --dry-run
   ```

8. **Backup before FORCE mode**
   ```bash
   # Backup Neon
   pg_dump $NEON_URL > backup.sql
   
   # Backup SQLite
   cp db.sqlite3 db.sqlite3.backup
   ```

### Migration from Old Sync

```bash
# 1. Clean up existing orphaned FKs
set DATABASE_URL=sqlite
python manage.py cleanup_orphaned_fks

# 2. Do initial FORCE sync to clean slate
python manage.py db_sync_v2 --direction neon_to_local --mode force

# 3. From now on, use MERGE mode
python manage.py db_sync_v2 --direction bidirectional --mode merge --cleanup-orphans
```

### Automation

**Daily cron job:**
```bash
#!/bin/bash
# /etc/cron.daily/db-sync

cd /path/to/project
source venv/bin/activate

# Bidirectional sync with cleanup
python manage.py db_sync_v2 \
    --direction bidirectional \
    --mode merge \
    --cleanup-orphans

# Check for orphans
python manage.py cleanup_orphaned_fks --dry-run
```

**Windows Task Scheduler:**
```powershell
# daily-sync.ps1
cd D:\PsyChoNyMouz\Projects\BusinessWebsite\Business-Management-System
python manage.py db_sync_v2 --direction bidirectional --mode merge --cleanup-orphans
```

### Summary

| Scenario | Command |
|----------|---------|
| **Daily production sync** | `db_sync_v2 --direction bidirectional --mode merge --cleanup-orphans` |
| **Initial setup** | `db_sync_v2 --direction neon_to_local --mode force` |
| **After offline work** | `db_sync_v2 --direction local_to_neon --mode merge` |
| **After schema change** | `db_sync_v2 --direction neon_to_local --mode force` |
| **Clean orphaned FKs** | `cleanup_orphaned_fks` |
| **Preview changes** | `db_sync_v2 ... --dry-run` |

**Key Takeaway:** Always use `--cleanup-orphans` and `--mode merge` for production syncs to maintain FK integrity and handle conflicts properly!
