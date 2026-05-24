#!/usr/bin/env python
"""
Fix orphaned foreign key references in the local SQLite database.
This script identifies and removes records with invalid FK references.

Usage:
    python fix_orphaned_fks.py
"""
import os
import sys
import django

# Setup Django
os.environ['DATABASE_URL'] = 'sqlite'  # Force offline mode
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'inventory_system.settings')
django.setup()

from django.db import connection

def find_orphaned_fks():
    """Find all orphaned foreign key references."""
    orphans = []
    
    with connection.cursor() as cursor:
        # Get all tables
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name NOT LIKE 'sqlite_%'
            AND name NOT LIKE 'django_%'
        """)
        tables = [row[0] for row in cursor.fetchall()]
        
        print(f"Checking {len(tables)} tables for orphaned FKs...\n")
        
        for table in tables:
            try:
                # Get FK info for this table
                cursor.execute(f'PRAGMA foreign_key_list("{table}")')
                fks = cursor.fetchall()
                
                if not fks:
                    continue
                
                for fk in fks:
                    fk_id = fk[0]
                    ref_table = fk[2]
                    fk_column = fk[3]
                    ref_column = fk[4]
                    
                    # Check if referenced table exists
                    cursor.execute(f"""
                        SELECT name FROM sqlite_master 
                        WHERE type='table' AND name='{ref_table}'
                    """)
                    if not cursor.fetchone():
                        print(f"⚠️  Table '{table}' references non-existent table '{ref_table}'")
                        continue
                    
                    # Find orphaned records
                    cursor.execute(f"""
                        SELECT t.rowid, t."{fk_column}"
                        FROM "{table}" t
                        LEFT JOIN "{ref_table}" r ON t."{fk_column}" = r."{ref_column}"
                        WHERE t."{fk_column}" IS NOT NULL
                          AND r."{ref_column}" IS NULL
                        LIMIT 10
                    """)
                    
                    orphaned_rows = cursor.fetchall()
                    if orphaned_rows:
                        orphans.append({
                            'table': table,
                            'fk_column': fk_column,
                            'ref_table': ref_table,
                            'ref_column': ref_column,
                            'rows': orphaned_rows
                        })
                        
                        print(f"❌ Found {len(orphaned_rows)} orphaned FK(s) in '{table}'")
                        print(f"   Column: {fk_column} -> {ref_table}.{ref_column}")
                        for rowid, fk_value in orphaned_rows[:5]:
                            print(f"   - rowid={rowid}, {fk_column}={fk_value} (missing in {ref_table})")
                        if len(orphaned_rows) > 5:
                            print(f"   ... and {len(orphaned_rows) - 5} more")
                        print()
                        
            except Exception as e:
                print(f"⚠️  Error checking table '{table}': {e}")
    
    return orphans

def fix_orphaned_fks(orphans, dry_run=True):
    """Remove orphaned records."""
    total_deleted = 0
    
    if dry_run:
        print("\n" + "="*70)
        print("DRY RUN - No changes will be made")
        print("="*70)
        print(f"\nWould delete {sum(len(o['rows']) for o in orphans)} orphaned records")
        return 0
    
    print("\n" + "="*70)
    print("FIXING ORPHANED FKs")
    print("="*70)
    
    with connection.cursor() as cursor:
        for orphan in orphans:
            table = orphan['table']
            fk_column = orphan['fk_column']
            ref_table = orphan['ref_table']
            
            try:
                # Delete orphaned records
                cursor.execute(f"""
                    DELETE FROM "{table}"
                    WHERE rowid IN (
                        SELECT t.rowid
                        FROM "{table}" t
                        LEFT JOIN "{ref_table}" r ON t."{fk_column}" = r."{ref_column}"
                        WHERE t."{fk_column}" IS NOT NULL
                          AND r."{ref_column}" IS NULL
                    )
                """)
                
                deleted = cursor.rowcount
                total_deleted += deleted
                print(f"✓ Deleted {deleted} orphaned record(s) from '{table}'")
                
            except Exception as e:
                print(f"✗ Error fixing '{table}': {e}")
    
    return total_deleted

def main():
    print("="*70)
    print("Orphaned Foreign Key Fixer")
    print("="*70)
    print()
    
    # Find orphans
    orphans = find_orphaned_fks()
    
    if not orphans:
        print("✓ No orphaned foreign keys found!")
        return 0
    
    print("\n" + "="*70)
    print(f"Summary: Found orphaned FKs in {len(orphans)} table(s)")
    print("="*70)
    
    # Ask user what to do
    print("\nOptions:")
    print("  1. Fix automatically (delete orphaned records)")
    print("  2. Show details only (dry run)")
    print("  3. Exit")
    
    choice = input("\nEnter choice (1-3): ").strip()
    
    if choice == '1':
        confirm = input("\n⚠️  This will DELETE orphaned records. Continue? (yes/no): ").strip().lower()
        if confirm == 'yes':
            deleted = fix_orphaned_fks(orphans, dry_run=False)
            print(f"\n✓ Fixed! Deleted {deleted} orphaned record(s)")
            print("\nYou can now run: python manage.py db_sync --direction neon_to_local")
        else:
            print("\nCancelled.")
    elif choice == '2':
        fix_orphaned_fks(orphans, dry_run=True)
    else:
        print("\nExiting.")
    
    return 0

if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\nCancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nError: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
