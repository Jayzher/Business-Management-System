# Troubleshooting: "Database is Locked" Error

## Problem
You're seeing this error:
```
django.db.utils.OperationalError: database is locked
```

## Root Cause Analysis

### Primary Cause: Multiple Django Processes
The most common cause is **multiple Django server processes** accessing the same SQLite database file simultaneously.

**How to check:**
```powershell
Get-Process python* | Where-Object { 
    (Get-CimInstance Win32_Process -Filter "ProcessId = $($_.Id)").CommandLine -like "*manage.py*runserver*" 
}
```

If you see **more than 2 processes** (Django runserver spawns 2: parent + worker), you have duplicate servers running.

### Secondary Cause: Large WAL File
SQLite's Write-Ahead Log (WAL) file can grow very large if checkpoints aren't happening properly.

**How to check:**
```powershell
dir db.sqlite3* | Select-Object Name, Length
```

If `db.sqlite3-wal` is **>10MB**, it needs to be checkpointed.

## Quick Fix (Recommended)

### Option 1: Use the PowerShell Script
```powershell
.\fix_database_lock.ps1
```

This script will:
1. Stop all Django processes
2. Checkpoint the WAL file
3. Verify database settings
4. Show you how to restart properly

### Option 2: Use the Python Script
```bash
# Stop Django first
Get-Process python* | Where-Object { (Get-CimInstance Win32_Process -Filter "ProcessId = $($_.Id)").CommandLine -like "*manage.py*runserver*" } | Stop-Process -Force

# Wait a few seconds
Start-Sleep -Seconds 3

# Run checkpoint
python checkpoint_wal.py
```

## Manual Fix (Step-by-Step)

### Step 1: Stop All Django Processes
```powershell
# Find Django processes
Get-Process python* | Where-Object { 
    (Get-CimInstance Win32_Process -Filter "ProcessId = $($_.Id)").CommandLine -like "*manage.py*runserver*" 
}

# Stop them
Get-Process python* | Where-Object { 
    (Get-CimInstance Win32_Process -Filter "ProcessId = $($_.Id)").CommandLine -like "*manage.py*runserver*" 
} | Stop-Process -Force

# Wait for processes to fully stop
Start-Sleep -Seconds 3
```

### Step 2: Checkpoint the WAL File
```bash
python -c "import sqlite3; conn = sqlite3.connect('db.sqlite3', timeout=60); conn.execute('PRAGMA wal_checkpoint(TRUNCATE);'); conn.commit(); conn.close(); print('Checkpoint complete')"
```

### Step 3: Verify Database Settings
```bash
python -c "import django, os; os.environ['DJANGO_SETTINGS_MODULE']='inventory_system.settings'; django.setup(); from django.db import connections; c=connections['local_cache'].cursor(); c.execute('PRAGMA journal_mode'); print('journal_mode:', c.fetchone()[0]); c.execute('PRAGMA busy_timeout'); print('busy_timeout:', c.fetchone()[0], 'ms'); c.execute('PRAGMA wal_autocheckpoint'); print('wal_autocheckpoint:', c.fetchone()[0])"
```

Expected output:
```
journal_mode: wal
busy_timeout: 60000 ms
wal_autocheckpoint: 10000
```

### Step 4: Start Django (ONLY ONCE!)
```bash
python manage.py runserver
```

**⚠️ CRITICAL:** Do NOT start multiple instances! Only run `python manage.py runserver` once.

## Prevention

### 1. Always Check Before Starting
Before starting Django, check if it's already running:
```powershell
Get-Process python* | Where-Object { 
    (Get-CimInstance Win32_Process -Filter "ProcessId = $($_.Id)").CommandLine -like "*manage.py*runserver*" 
}
```

### 2. Use a Process Manager
Consider using a process manager like:
- **Supervisor** (Linux/Mac)
- **PM2** (Cross-platform)
- **Windows Service** (Windows)

These ensure only one instance runs at a time.

### 3. Regular WAL Checkpoints
Add a management command to checkpoint the WAL file regularly:

```python
# management/commands/checkpoint_wal.py
from django.core.management.base import BaseCommand
from django.db import connections

class Command(BaseCommand):
    help = 'Checkpoint the SQLite WAL file'

    def handle(self, *args, **options):
        conn = connections['local_cache']
        cursor = conn.cursor()
        cursor.execute('PRAGMA wal_checkpoint(TRUNCATE);')
        self.stdout.write(self.style.SUCCESS('WAL checkpoint complete'))
```

Run it periodically:
```bash
python manage.py checkpoint_wal
```

### 4. Monitor WAL File Size
Add this to your monitoring/health check:
```python
import os

wal_path = 'db.sqlite3-wal'
if os.path.exists(wal_path):
    wal_size_mb = os.path.getsize(wal_path) / (1024 * 1024)
    if wal_size_mb > 10:
        # Alert: WAL file is too large
        print(f"WARNING: WAL file is {wal_size_mb:.2f} MB")
```

## Understanding SQLite WAL Mode

### What is WAL?
Write-Ahead Logging (WAL) is a SQLite journal mode that allows:
- ✅ Multiple readers simultaneously
- ✅ One writer + multiple readers simultaneously
- ✅ Better concurrency than default DELETE mode

### How WAL Works
1. Writes go to the WAL file (`db.sqlite3-wal`)
2. Reads come from the main database + WAL file
3. Periodically, WAL is "checkpointed" (merged back to main database)

### WAL Checkpointing
Checkpoints happen automatically when:
- WAL file reaches `wal_autocheckpoint` pages (we set it to 10000)
- All connections close
- Manual checkpoint is triggered

### Why Locks Still Happen
Even with WAL mode, locks can occur when:
1. **Multiple processes** try to write simultaneously
2. **Checkpoint is running** (briefly locks the database)
3. **WAL file is too large** (checkpoint takes longer)
4. **busy_timeout expires** (we set it to 60s, but if lock lasts longer, it fails)

## Advanced Debugging

### Check Active Connections
```python
import sqlite3
conn = sqlite3.connect('db.sqlite3')
cursor = conn.cursor()
cursor.execute("PRAGMA database_list;")
print(cursor.fetchall())
conn.close()
```

### Check WAL File Contents
```bash
python -c "import sqlite3; conn = sqlite3.connect('db.sqlite3'); cursor = conn.cursor(); cursor.execute('PRAGMA wal_checkpoint(PASSIVE);'); print('Checkpoint result:', cursor.fetchone()); conn.close()"
```

### Force Checkpoint (Aggressive)
```bash
python -c "import sqlite3; conn = sqlite3.connect('db.sqlite3'); cursor = conn.cursor(); cursor.execute('PRAGMA wal_checkpoint(RESTART);'); print('Checkpoint result:', cursor.fetchone()); conn.close()"
```

### Disable WAL Mode (Not Recommended)
```bash
python -c "import sqlite3; conn = sqlite3.connect('db.sqlite3'); cursor = conn.cursor(); cursor.execute('PRAGMA journal_mode=DELETE;'); print('Journal mode:', cursor.fetchone()[0]); conn.close()"
```

**⚠️ Warning:** Disabling WAL mode will make the database slower and more prone to locks.

## When to Use PostgreSQL Instead

Consider migrating to PostgreSQL if:
1. You have **multiple concurrent users** (>10)
2. You need **true multi-process concurrency**
3. You're experiencing **frequent lock errors** even after fixes
4. Your database is **>1GB**
5. You need **advanced features** (full-text search, JSON queries, etc.)

SQLite is excellent for:
- ✅ Single-user applications
- ✅ Development/testing
- ✅ Embedded applications
- ✅ Read-heavy workloads
- ✅ Small to medium databases (<1GB)

## Related Files
- `DATABASE_LOCK_FIX.md` - Details of the code fixes applied
- `fix_database_lock.ps1` - Automated fix script (PowerShell)
- `checkpoint_wal.py` - WAL checkpoint tool (Python)
- `sync/background_sync.py` - Background worker implementation
- `inventory_system/settings.py` - SQLite PRAGMA settings

## Support
If you continue to experience issues after following this guide:
1. Check the Django logs for more details
2. Verify only ONE Django process is running
3. Ensure the WAL file is <10MB
4. Consider using PostgreSQL for production
