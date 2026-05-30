# Quick Start: Database Sync V2

## TL;DR - Just Run This

```bash
# Daily production sync (recommended)
python manage.py db_sync_v2 --direction bidirectional --mode merge --cleanup-orphans
```

That's it! This command will:
- ✓ Clean up orphaned FKs on both databases
- ✓ Sync Neon → Local (Neon is source of truth)
- ✓ Sync Local → Neon (new local changes)
- ✓ Handle conflicts intelligently (newer timestamp wins)
- ✓ Validate FK integrity after sync

## What Changed?

### Old Sync (db_sync)
```bash
python manage.py db_sync --direction neon_to_local
```
**Problems:**
- ✗ `ignore_conflicts=True` silently skipped records
- ✗ Created orphaned FKs
- ✗ No conflict resolution
- ✗ Overwrote everything (destructive)

### New Sync (db_sync_v2)
```bash
python manage.py db_sync_v2 --direction bidirectional --mode merge --cleanup-orphans
```
**Benefits:**
- ✓ Smart conflict resolution (timestamp-based)
- ✓ Automatic orphaned FK cleanup
- ✓ Priority system (Neon = source of truth)
- ✓ FK integrity validation
- ✓ Non-destructive merging

## Common Commands

### 1. Daily Sync (Production)
```bash
python manage.py db_sync_v2 --direction bidirectional --mode merge --cleanup-orphans
```
Use this every day to keep both databases in sync.

### 2. Initial Setup (New Device)
```bash
python manage.py db_sync_v2 --direction neon_to_local --mode force
```
Use this once when setting up a new device.

### 3. After Offline Work
```bash
python manage.py db_sync_v2 --direction local_to_neon --mode merge --cleanup-orphans
```
Use this to push local changes to Neon after working offline.

### 4. Preview Changes (Dry Run)
```bash
python manage.py db_sync_v2 --direction bidirectional --mode merge --dry-run
```
Use this to see what would be synced without actually syncing.

### 5. Clean Orphaned FKs Only
```bash
set DATABASE_URL=sqlite
python manage.py cleanup_orphaned_fks
```
Use this to clean up orphaned FKs without syncing.

## Troubleshooting

### "Orphaned FKs found after sync"
```bash
# Clean and re-sync
python manage.py db_sync_v2 --direction bidirectional --mode merge --cleanup-orphans
```

### "FK constraint failed"
```bash
# Force clean slate from Neon
python manage.py db_sync_v2 --direction neon_to_local --mode force
```

### "Sync is slow"
```bash
# Use force mode for initial sync
python manage.py db_sync_v2 --direction neon_to_local --mode force

# Then use merge mode for daily syncs
python manage.py db_sync_v2 --direction bidirectional --mode merge --cleanup-orphans
```

## Migration from Old Sync

```bash
# Step 1: Clean up existing orphans
set DATABASE_URL=sqlite
python manage.py cleanup_orphaned_fks

# Step 2: Do initial force sync
python manage.py db_sync_v2 --direction neon_to_local --mode force

# Step 3: From now on, use merge mode
python manage.py db_sync_v2 --direction bidirectional --mode merge --cleanup-orphans
```

## Automation

### Windows Task Scheduler
Create `daily-sync.bat`:
```batch
@echo off
cd /d D:\PsyChoNyMouz\Projects\BusinessWebsite\Business-Management-System
python manage.py db_sync_v2 --direction bidirectional --mode merge --cleanup-orphans
pause
```

Schedule it to run daily at 2 AM.

### Linux Cron
Add to crontab:
```bash
0 2 * * * cd /path/to/project && python manage.py db_sync_v2 --direction bidirectional --mode merge --cleanup-orphans
```

## Key Differences

| Feature | Old Sync | New Sync V2 |
|---------|----------|-------------|
| Conflict Resolution | ✗ None (overwrites) | ✓ Timestamp-based |
| Orphaned FK Cleanup | ✗ Manual | ✓ Automatic |
| Priority System | ✗ None | ✓ Neon is source of truth |
| FK Validation | ✗ After sync only | ✓ Before & after |
| Merge Mode | ✗ No | ✓ Yes |
| Dry Run | ✓ Yes | ✓ Yes |
| Bidirectional | ✗ No | ✓ Yes |

## When to Use Which Mode?

### MERGE Mode (Recommended)
- Daily syncs
- Multiple users
- Want to preserve changes from both sides
- Production environment

### FORCE Mode
- Initial setup
- After schema changes
- When destination is corrupted
- When you want a clean slate

## Summary

**For 99% of cases, just run:**
```bash
python manage.py db_sync_v2 --direction bidirectional --mode merge --cleanup-orphans
```

This will handle everything automatically and keep your databases in perfect sync!
