#!/usr/bin/env python
"""
Sync data from Neon (remote PostgreSQL) to local SQLite database.

This script:
1. Exports data from Neon using dumpdata
2. Imports data into local SQLite using loaddata

Usage:
    python sync_neon_to_local.py
"""
import os
import sys
import subprocess
import tempfile

def run_command(cmd, env=None):
    """Run a command and return the result."""
    print(f"Running: {' '.join(cmd)}")
    print()
    result = subprocess.run(cmd, env=env, text=True, capture_output=True)
    
    # Print stdout
    if result.stdout:
        print(result.stdout)
    
    # Print stderr
    if result.stderr:
        print("STDERR:", result.stderr, file=sys.stderr)
    
    if result.returncode != 0:
        print(f"\nCommand failed with exit code: {result.returncode}")
        return False
    return True

def main():
    print("="*70)
    print("Neon → Local SQLite Sync")
    print("="*70)
    print()

    # Step 1: Export from Neon (OFFLINE_MODE=0)
    print("Step 1: Exporting data from Neon database...")
    print("-" * 70)
    
    neon_env = os.environ.copy()
    neon_env['OFFLINE_MODE'] = '0'  # Use Neon
    
    # Create temp file for export
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as tmp_file:
        tmp_filename = tmp_file.name
    
    print(f"Temp file: {tmp_filename}")
    print()
    
    # Export catalog data from Neon
    export_cmd = [
        sys.executable,
        'manage.py',
        'dumpdata',
        'catalog.Category',
        'catalog.Unit',
        'catalog.UnitConversion',
        'catalog.Item',
        '--output', tmp_filename,
        '--format', 'json',
        '--indent', '2',
    ]
    
    if not run_command(export_cmd, env=neon_env):
        print("Failed to export from Neon")
        os.unlink(tmp_filename)
        return 1
    
    print("✓ Export completed")
    print()
    
    # Validate JSON before importing
    print("Validating exported JSON...")
    try:
        import json
        with open(tmp_filename, 'r', encoding='utf-8') as f:
            data = json.load(f)
        print(f"✓ Valid JSON with {len(data)} records")
        print()
    except json.JSONDecodeError as e:
        print(f"✗ Invalid JSON in exported file: {e}")
        print("\nFirst 500 characters of the file:")
        with open(tmp_filename, 'r', encoding='utf-8') as f:
            print(f.read(500))
        os.unlink(tmp_filename)
        return 1
    except Exception as e:
        print(f"✗ Error reading exported file: {e}")
        os.unlink(tmp_filename)
        return 1

    # Step 2: Import to local SQLite (OFFLINE_MODE=1)
    print("Step 2: Importing data to local SQLite database...")
    print("-" * 70)
    
    local_env = os.environ.copy()
    local_env['OFFLINE_MODE'] = '1'  # Use SQLite
    
    # Import data into SQLite
    import_cmd = [
        sys.executable,
        'manage.py',
        'loaddata',
        tmp_filename,
    ]
    
    if not run_command(import_cmd, env=local_env):
        print("Failed to import to SQLite")
        os.unlink(tmp_filename)
        return 1
    
    print("✓ Import completed")
    print()

    # Clean up
    os.unlink(tmp_filename)
    print("✓ Temp file cleaned up")
    print()

    print("="*70)
    print("✓ Sync completed successfully!")
    print("="*70)
    print()
    print("Your local SQLite database now has the latest data from Neon.")
    print()
    
    return 0

if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\nSync cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nError: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
