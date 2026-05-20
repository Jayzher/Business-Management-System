#!/usr/bin/env python
"""
Checkpoint the SQLite WAL file to merge it back to the main database.

This should be run when:
1. The WAL file is very large (>10MB)
2. You're experiencing "database is locked" errors
3. Before backing up the database

Usage:
    python checkpoint_wal.py
"""

import os
import sqlite3
import sys


def checkpoint_wal(db_path='db.sqlite3'):
    """Checkpoint the WAL file for the given database."""
    
    if not os.path.exists(db_path):
        print(f"❌ Database file not found: {db_path}")
        return False
    
    wal_path = f"{db_path}-wal"
    wal_size_before = 0
    
    if os.path.exists(wal_path):
        wal_size_before = os.path.getsize(wal_path) / (1024 * 1024)  # MB
        print(f"📊 WAL file size before: {wal_size_before:.2f} MB")
    else:
        print("ℹ️  No WAL file found (database might not be in WAL mode)")
    
    try:
        print(f"🔄 Connecting to {db_path}...")
        conn = sqlite3.connect(db_path, timeout=60)
        
        # Ensure WAL mode is enabled
        cursor = conn.cursor()
        cursor.execute('PRAGMA journal_mode=WAL;')
        journal_mode = cursor.fetchone()[0]
        print(f"✓ Journal mode: {journal_mode}")
        
        # Perform checkpoint
        print("🔄 Running WAL checkpoint (TRUNCATE)...")
        cursor.execute('PRAGMA wal_checkpoint(TRUNCATE);')
        result = cursor.fetchone()
        print(f"✓ Checkpoint result: {result}")
        
        # Commit and close
        conn.commit()
        conn.close()
        
        # Check WAL file size after
        if os.path.exists(wal_path):
            wal_size_after = os.path.getsize(wal_path) / (1024 * 1024)  # MB
            print(f"📊 WAL file size after: {wal_size_after:.2f} MB")
            
            if wal_size_after < wal_size_before:
                reduction = wal_size_before - wal_size_after
                print(f"✅ WAL file reduced by {reduction:.2f} MB!")
            elif wal_size_after == 0:
                print("✅ WAL file is now empty!")
            else:
                print(f"⚠️  WAL file size unchanged (might still be in use)")
        else:
            print("✅ WAL file removed (checkpoint successful)")
        
        return True
        
    except sqlite3.OperationalError as e:
        print(f"❌ Database is locked: {e}")
        print("\nℹ️  This usually means:")
        print("   1. Django server is still running")
        print("   2. Another process is accessing the database")
        print("   3. A transaction is still open")
        print("\n💡 Solution:")
        print("   1. Stop all Django processes: Get-Process python* | Stop-Process")
        print("   2. Wait a few seconds")
        print("   3. Run this script again")
        return False
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def check_django_processes():
    """Check if Django processes are running (Windows only)."""
    try:
        import subprocess
        result = subprocess.run(
            ['powershell', '-Command', 
             'Get-Process python* -ErrorAction SilentlyContinue | '
             'Where-Object { (Get-CimInstance Win32_Process -Filter "ProcessId = $($_.Id)").CommandLine -like "*manage.py*runserver*" } | '
             'Measure-Object | Select-Object -ExpandProperty Count'],
            capture_output=True,
            text=True,
            timeout=5
        )
        count = int(result.stdout.strip() or 0)
        if count > 0:
            print(f"⚠️  Warning: {count} Django process(es) still running!")
            print("   Stop them first: Get-Process python* | Where-Object { (Get-CimInstance Win32_Process -Filter \"ProcessId = `$(`$_.Id)\").CommandLine -like \"*manage.py*runserver*\" } | Stop-Process -Force")
            return count
    except Exception:
        pass
    return 0


if __name__ == '__main__':
    print("=" * 60)
    print("SQLite WAL Checkpoint Tool")
    print("=" * 60)
    print()
    
    # Check for running Django processes
    django_count = check_django_processes()
    if django_count > 0:
        response = input("\nContinue anyway? (y/N): ")
        if response.lower() != 'y':
            print("Aborted.")
            sys.exit(1)
    
    print()
    success = checkpoint_wal()
    
    print()
    print("=" * 60)
    if success:
        print("✅ Checkpoint completed successfully!")
        print()
        print("You can now start the Django server:")
        print("  python manage.py runserver")
        print()
        print("⚠️  IMPORTANT: Start ONLY ONE instance of the server!")
    else:
        print("❌ Checkpoint failed. See errors above.")
        sys.exit(1)
    print("=" * 60)
