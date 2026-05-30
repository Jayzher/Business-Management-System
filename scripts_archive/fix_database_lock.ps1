# Fix Database Lock Issue
# This script stops all Django processes, checkpoints the WAL file, and restarts the server

Write-Host "=== Database Lock Fix Script ===" -ForegroundColor Cyan
Write-Host ""

# Step 1: Stop all Django processes
Write-Host "Step 1: Stopping all Django processes..." -ForegroundColor Yellow
$djangoProcesses = Get-Process python* -ErrorAction SilentlyContinue | Where-Object {
    $cmdLine = (Get-CimInstance Win32_Process -Filter "ProcessId = $($_.Id)" -ErrorAction SilentlyContinue).CommandLine
    $cmdLine -like "*manage.py*runserver*"
}

if ($djangoProcesses) {
    Write-Host "Found $($djangoProcesses.Count) Django process(es):" -ForegroundColor Yellow
    $djangoProcesses | ForEach-Object {
        Write-Host "  - PID $($_.Id): $($_.ProcessName)" -ForegroundColor Gray
        Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Seconds 2
    Write-Host "All Django processes stopped." -ForegroundColor Green
} else {
    Write-Host "No Django processes found." -ForegroundColor Green
}

# Step 2: Checkpoint the WAL file
Write-Host ""
Write-Host "Step 2: Checkpointing WAL file..." -ForegroundColor Yellow

# Check WAL file size before
$walFile = "db.sqlite3-wal"
if (Test-Path $walFile) {
    $walSizeBefore = (Get-Item $walFile).Length / 1MB
    Write-Host "WAL file size before: $([math]::Round($walSizeBefore, 2)) MB" -ForegroundColor Gray
} else {
    Write-Host "No WAL file found." -ForegroundColor Gray
}

# Run checkpoint
python -c @"
import sqlite3
import os

db_path = 'db.sqlite3'
if os.path.exists(db_path):
    conn = sqlite3.connect(db_path, timeout=60)
    conn.execute('PRAGMA journal_mode=WAL;')
    conn.execute('PRAGMA wal_checkpoint(TRUNCATE);')
    conn.commit()
    conn.close()
    print('WAL checkpoint completed successfully.')
else:
    print('Database file not found.')
"@

# Check WAL file size after
if (Test-Path $walFile) {
    $walSizeAfter = (Get-Item $walFile).Length / 1MB
    Write-Host "WAL file size after: $([math]::Round($walSizeAfter, 2)) MB" -ForegroundColor Gray
    
    if ($walSizeAfter -lt $walSizeBefore) {
        Write-Host "WAL file successfully reduced!" -ForegroundColor Green
    }
} else {
    Write-Host "WAL file removed (checkpoint successful)." -ForegroundColor Green
}

# Step 3: Verify database settings
Write-Host ""
Write-Host "Step 3: Verifying database settings..." -ForegroundColor Yellow
python -c @"
import django
import os
os.environ['DJANGO_SETTINGS_MODULE'] = 'inventory_system.settings'
django.setup()

from django.db import connections

c = connections['local_cache'].cursor()
c.execute('PRAGMA journal_mode')
journal_mode = c.fetchone()[0]
c.execute('PRAGMA busy_timeout')
busy_timeout = c.fetchone()[0]
c.execute('PRAGMA wal_autocheckpoint')
wal_autocheckpoint = c.fetchone()[0]

print(f'journal_mode: {journal_mode}')
print(f'busy_timeout: {busy_timeout} ms')
print(f'wal_autocheckpoint: {wal_autocheckpoint}')

connections['local_cache'].close()
"@

Write-Host ""
Write-Host "=== Fix Complete ===" -ForegroundColor Green
Write-Host ""
Write-Host "You can now start the Django server with:" -ForegroundColor Cyan
Write-Host "  python manage.py runserver" -ForegroundColor White
Write-Host ""
Write-Host "IMPORTANT: Make sure to start ONLY ONE instance of the server!" -ForegroundColor Yellow
