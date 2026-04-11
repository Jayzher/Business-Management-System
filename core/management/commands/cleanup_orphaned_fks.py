"""
Management command: cleanup_orphaned_fks
=========================================
Finds and removes orphaned foreign key references across all tables.
This fixes data integrity issues that prevent migrations from running.

Usage:
    python manage.py cleanup_orphaned_fks                # all tables
    python manage.py cleanup_orphaned_fks --dry-run      # preview only
    python manage.py cleanup_orphaned_fks --table sales_salespickupline
"""
from django.core.management.base import BaseCommand
from django.db import connection, transaction
from django.apps import apps


class Command(BaseCommand):
    help = 'Find and remove orphaned foreign key references'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Preview orphans without deleting',
        )
        parser.add_argument(
            '--table',
            type=str,
            help='Check specific table only',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        specific_table = options.get('table')

        mode = 'DRY-RUN' if dry_run else 'APPLYING'
        self.stdout.write(self.style.SUCCESS(f'\n=== Cleanup Orphaned FKs [{mode}] ===\n'))

        total_orphans = 0
        total_deleted = 0

        with connection.cursor() as cursor:
            # Get all tables
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name NOT LIKE 'sqlite_%'
                ORDER BY name
            """)
            tables = [row[0] for row in cursor.fetchall()]

            if specific_table:
                if specific_table in tables:
                    tables = [specific_table]
                else:
                    self.stdout.write(self.style.ERROR(f'Table {specific_table} not found'))
                    return

            for table in tables:
                orphans = self._check_table(cursor, table)
                if orphans:
                    total_orphans += len(orphans)
                    self.stdout.write(self.style.WARNING(
                        f'\n{table}: Found {len(orphans)} orphaned record(s)'
                    ))
                    
                    for orphan in orphans[:10]:  # Show first 10
                        self.stdout.write(f'  Row ID {orphan["row_id"]} -> '
                                        f'{orphan["fk_column"]}={orphan["fk_value"]} '
                                        f'(missing in {orphan["ref_table"]})')
                    
                    if len(orphans) > 10:
                        self.stdout.write(f'  ... and {len(orphans) - 10} more')

                    if not dry_run:
                        deleted = self._delete_orphans(cursor, table, orphans)
                        total_deleted += deleted
                        self.stdout.write(self.style.SUCCESS(f'  Deleted {deleted} orphaned record(s)'))

        self.stdout.write(self.style.SUCCESS(f'\n=== Summary ==='))
        self.stdout.write(f'Total orphaned records found: {total_orphans}')
        if not dry_run:
            self.stdout.write(f'Total records deleted: {total_deleted}')
        else:
            self.stdout.write(self.style.WARNING('Dry-run mode - no changes made'))

    def _check_table(self, cursor, table):
        """Check a table for orphaned FK references."""
        orphans = []

        # Get FK info for this table
        cursor.execute(f'PRAGMA foreign_key_list("{table}")')
        fks = cursor.fetchall()

        if not fks:
            return orphans

        for fk in fks:
            fk_id = fk[0]
            fk_seq = fk[1]
            ref_table = fk[2]
            fk_column = fk[3]
            ref_column = fk[4]

            # Find orphaned rows
            query = f"""
                SELECT t.rowid, t."{fk_column}"
                FROM "{table}" t
                LEFT JOIN "{ref_table}" r ON t."{fk_column}" = r."{ref_column}"
                WHERE t."{fk_column}" IS NOT NULL
                  AND r."{ref_column}" IS NULL
            """
            
            try:
                cursor.execute(query)
                for row in cursor.fetchall():
                    orphans.append({
                        'row_id': row[0],
                        'fk_column': fk_column,
                        'fk_value': row[1],
                        'ref_table': ref_table,
                        'ref_column': ref_column,
                    })
            except Exception as e:
                self.stdout.write(self.style.ERROR(
                    f'  Error checking {table}.{fk_column}: {e}'
                ))

        return orphans

    def _delete_orphans(self, cursor, table, orphans):
        """Delete orphaned records."""
        if not orphans:
            return 0

        row_ids = [o['row_id'] for o in orphans]
        
        # Delete in batches of 500
        deleted = 0
        for i in range(0, len(row_ids), 500):
            batch = row_ids[i:i+500]
            placeholders = ','.join(str(rid) for rid in batch)
            cursor.execute(f'DELETE FROM "{table}" WHERE rowid IN ({placeholders})')
            deleted += cursor.rowcount

        return deleted
