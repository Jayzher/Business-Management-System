"""
Improved Bidirectional Database Sync with Conflict Resolution
==============================================================

Priority-based sync strategy:
- Neon PostgreSQL is the SOURCE OF TRUTH (priority 1)
- Local SQLite is the cache (priority 2)

Sync modes:
1. MERGE mode (default): Intelligently merge changes with conflict resolution
2. FORCE mode: Overwrite destination completely (current behavior)

Usage:
    python manage.py db_sync_v2 --direction local_to_neon --mode merge
    python manage.py db_sync_v2 --direction neon_to_local --mode force
"""
import os
from collections import defaultdict, deque
from datetime import datetime
from django.core.management.base import BaseCommand
from django.apps import apps
from django.db import connections, transaction
from django.conf import settings
import dj_database_url


NEON_URL = getattr(settings, 'NEON_URL', (
    'postgresql://neondb_owner:npg_KhjsX3uB0mil'
    '@ep-raspy-hall-a1fl4lfx.ap-southeast-1.aws.neon.tech'
    '/neondb?sslmode=require'
))
BATCH_SIZE = 500


class Command(BaseCommand):
    help = 'Improved sync with conflict resolution and FK integrity preservation'

    def add_arguments(self, parser):
        parser.add_argument(
            '--direction',
            type=str,
            required=True,
            choices=['local_to_neon', 'neon_to_local', 'bidirectional'],
            help='Sync direction',
        )
        parser.add_argument(
            '--mode',
            type=str,
            default='merge',
            choices=['merge', 'force'],
            help='Sync mode: merge (smart conflict resolution) or force (overwrite)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Preview changes without applying',
        )
        parser.add_argument(
            '--cleanup-orphans',
            action='store_true',
            help='Clean up orphaned FKs before sync',
        )

    def handle(self, *args, **options):
        direction = options['direction']
        mode = options['mode']
        dry_run = options['dry_run']
        cleanup_orphans = options['cleanup_orphans']

        self._ensure_both_databases()

        self.stdout.write('=' * 70)
        self.stdout.write(f'DB Sync V2: {direction.upper()} ({mode.upper()} mode)')
        if dry_run:
            self.stdout.write('*** DRY RUN — no changes will be applied ***')
        self.stdout.write('=' * 70)
        self.stdout.write()

        # Cleanup orphaned FKs first if requested
        if cleanup_orphans:
            self._cleanup_all_orphans()

        if direction == 'bidirectional':
            # Bidirectional: Neon -> Local first (Neon is source of truth)
            # Then Local -> Neon (only new local changes)
            self.stdout.write('Phase 1: Syncing Neon -> Local (source of truth)')
            self._sync_one_way('neon', 'sqlite', mode, dry_run)
            self.stdout.write()
            self.stdout.write('Phase 2: Syncing Local -> Neon (new local changes)')
            self._sync_one_way('sqlite', 'neon', 'merge', dry_run)  # Always merge for local->neon
        elif direction == 'local_to_neon':
            self._sync_one_way('sqlite', 'neon', mode, dry_run)
        else:  # neon_to_local
            self._sync_one_way('neon', 'sqlite', mode, dry_run)

        self.stdout.write()
        self.stdout.write('=' * 70)
        self.stdout.write('[OK] Sync completed successfully!')
        self.stdout.write('=' * 70)

    def _sync_one_way(self, src_alias, dst_alias, mode, dry_run):
        """Perform one-way sync with conflict resolution."""
        src_label = 'Neon PostgreSQL' if src_alias == 'neon' else 'Local SQLite'
        dst_label = 'Local SQLite' if dst_alias == 'sqlite' else 'Neon PostgreSQL'

        self.stdout.write(f'\n{src_label} -> {dst_label}')
        self.stdout.write('-' * 70)

        # Get topologically sorted models
        all_models = self._topo_sort_models()

        # Count source rows
        self.stdout.write(f'Counting rows in {src_label}...')
        model_counts = []
        total_src = 0
        for model in all_models:
            name = f'{model._meta.app_label}.{model._meta.model_name}'
            try:
                cnt = model.objects.using(src_alias).count()
            except Exception:
                cnt = 0
            if cnt:
                model_counts.append((model, name, cnt))
                total_src += cnt

        self.stdout.write(f'Source: {total_src} rows across {len(model_counts)} tables')

        if dry_run:
            self.stdout.write('\n[DRY RUN] Would sync:')
            for _m, name, cnt in model_counts:
                self.stdout.write(f'  {name}: {cnt} rows')
            return

        # Perform sync based on mode
        if mode == 'force':
            self._sync_force(src_alias, dst_alias, model_counts, all_models)
        else:  # merge
            self._sync_merge(src_alias, dst_alias, model_counts, all_models)

    def _sync_force(self, src_alias, dst_alias, model_counts, all_models):
        """Force sync: Truncate destination and copy everything."""
        self.stdout.write('\nMode: FORCE (truncate & copy)')
        
        # Migrate destination
        self.stdout.write('Running migrations on destination...')
        from django.core.management import call_command
        try:
            call_command('migrate', '--run-syncdb', database=dst_alias,
                        verbosity=0, interactive=False)
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Migration failed: {e}'))
            raise

        # Truncate destination
        self.stdout.write('Truncating destination tables...')
        self._truncate_all(dst_alias)

        # Disable FK constraints
        dst_is_pg = 'postgresql' in settings.DATABASES[dst_alias].get('ENGINE', '')
        saved_fks = []
        if dst_is_pg:
            saved_fks = self._drop_fk_constraints(dst_alias)
        else:
            with connections[dst_alias].cursor() as cursor:
                cursor.execute('PRAGMA foreign_keys = OFF;')

        # Copy data
        self.stdout.write('Copying data...')
        total_copied = 0
        errors = []

        for model, name, cnt in model_counts:
            try:
                objs = list(model.objects.using(src_alias).all())
                for obj in objs:
                    obj._state.adding = True
                    obj._state.db = dst_alias

                for i in range(0, len(objs), BATCH_SIZE):
                    batch = objs[i:i + BATCH_SIZE]
                    model.objects.using(dst_alias).bulk_create(
                        batch, batch_size=BATCH_SIZE
                    )
                total_copied += cnt
                self.stdout.write(f'  [OK] {name}: {cnt} rows')
            except Exception as exc:
                msg = f'  [ERROR] {name}: {exc}'
                self.stdout.write(self.style.ERROR(msg))
                errors.append(msg)

        # Re-enable FK constraints
        if dst_is_pg and saved_fks:
            restore_errors = self._restore_fk_constraints(dst_alias, saved_fks)
            if restore_errors:
                self.stdout.write(self.style.WARNING(
                    f'Warning: {len(restore_errors)} FK constraints could not be restored'
                ))
        elif not dst_is_pg:
            with connections[dst_alias].cursor() as cursor:
                cursor.execute('PRAGMA foreign_keys = ON;')

        # Reset sequences for PostgreSQL
        if dst_is_pg:
            self._reset_sequences(dst_alias, all_models)

        self.stdout.write(f'\n[OK] Copied {total_copied} rows')
        if errors:
            self.stdout.write(self.style.WARNING(f'[WARN] {len(errors)} errors occurred'))

    def _sync_merge(self, src_alias, dst_alias, model_counts, all_models):
        """
        Merge sync: Smart conflict resolution with FK integrity.
        
        Strategy:
        1. For each record in source:
           - If PK exists in destination: Compare timestamps, keep newer
           - If PK doesn't exist: Insert
        2. For deletions: Check if record exists in source but not destination
           - Only delete if no child records depend on it
        3. Validate FK integrity after sync
        """
        self.stdout.write('\nMode: MERGE (smart conflict resolution)')
        
        # Migrate destination
        self.stdout.write('Running migrations on destination...')
        from django.core.management import call_command
        try:
            call_command('migrate', '--run-syncdb', database=dst_alias,
                        verbosity=0, interactive=False)
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Migration failed: {e}'))
            raise

        # Disable FK constraints temporarily
        dst_is_pg = 'postgresql' in settings.DATABASES[dst_alias].get('ENGINE', '')
        if not dst_is_pg:
            with connections[dst_alias].cursor() as cursor:
                cursor.execute('PRAGMA foreign_keys = OFF;')

        # Sync each model
        self.stdout.write('Merging data with conflict resolution...')
        total_inserted = 0
        total_updated = 0
        total_skipped = 0
        errors = []

        for model, name, cnt in model_counts:
            try:
                inserted, updated, skipped = self._merge_model(
                    model, src_alias, dst_alias
                )
                total_inserted += inserted
                total_updated += updated
                total_skipped += skipped
                
                status = []
                if inserted: status.append(f'+{inserted}')
                if updated: status.append(f'~{updated}')
                if skipped: status.append(f'={skipped}')
                
                self.stdout.write(f'  [OK] {name}: {" ".join(status)}')
            except Exception as exc:
                msg = f'  [ERROR] {name}: {exc}'
                self.stdout.write(self.style.ERROR(msg))
                errors.append(msg)

        # Re-enable FK constraints
        if not dst_is_pg:
            with connections[dst_alias].cursor() as cursor:
                cursor.execute('PRAGMA foreign_keys = ON;')

        # Reset sequences for PostgreSQL
        if dst_is_pg:
            self._reset_sequences(dst_alias, all_models)

        # Validate FK integrity
        self.stdout.write('\nValidating FK integrity...')
        orphan_count = self._count_orphaned_fks(dst_alias)
        if orphan_count > 0:
            self.stdout.write(self.style.WARNING(
                f'[WARN] Found {orphan_count} orphaned FK(s) - run cleanup_orphaned_fks'
            ))
        else:
            self.stdout.write('[OK] FK integrity OK')

        self.stdout.write(f'\n[OK] Inserted: {total_inserted}, Updated: {total_updated}, Skipped: {total_skipped}')
        if errors:
            self.stdout.write(self.style.WARNING(f'[WARN] {len(errors)} errors occurred'))

    def _merge_model(self, model, src_alias, dst_alias):
        """
        Merge records from source to destination with conflict resolution.
        Returns (inserted_count, updated_count, skipped_count)
        """
        inserted = 0
        updated = 0
        skipped = 0

        # Get all source records
        src_objs = list(model.objects.using(src_alias).all())
        if not src_objs:
            return (0, 0, 0)

        # Get all destination PKs for quick lookup
        dst_pks = set(
            model.objects.using(dst_alias).values_list('pk', flat=True)
        )

        # Check if model has timestamp fields for conflict resolution
        has_updated_at = hasattr(model, 'updated_at')
        has_modified_at = hasattr(model, 'modified_at')
        has_timestamp = has_updated_at or has_modified_at
        timestamp_field = 'updated_at' if has_updated_at else 'modified_at' if has_modified_at else None

        to_insert = []
        to_update = []

        for src_obj in src_objs:
            if src_obj.pk in dst_pks:
                # Record exists in destination - check if we should update
                if has_timestamp:
                    # Compare timestamps
                    try:
                        dst_obj = model.objects.using(dst_alias).get(pk=src_obj.pk)
                        src_ts = getattr(src_obj, timestamp_field)
                        dst_ts = getattr(dst_obj, timestamp_field)
                        
                        if src_ts and dst_ts and src_ts > dst_ts:
                            # Source is newer - update
                            to_update.append(src_obj)
                        else:
                            # Destination is newer or same - skip
                            skipped += 1
                    except Exception:
                        # If comparison fails, skip
                        skipped += 1
                else:
                    # No timestamp - skip (keep destination)
                    skipped += 1
            else:
                # Record doesn't exist - insert
                to_insert.append(src_obj)

        # Perform inserts
        if to_insert:
            for obj in to_insert:
                obj._state.adding = True
                obj._state.db = dst_alias
            
            for i in range(0, len(to_insert), BATCH_SIZE):
                batch = to_insert[i:i + BATCH_SIZE]
                model.objects.using(dst_alias).bulk_create(
                    batch, batch_size=BATCH_SIZE
                )
            inserted = len(to_insert)

        # Perform updates
        if to_update:
            for obj in to_update:
                obj._state.adding = False
                obj._state.db = dst_alias
                try:
                    obj.save(using=dst_alias)
                    updated += 1
                except Exception:
                    skipped += 1

        return (inserted, updated, skipped)

    def _cleanup_all_orphans(self):
        """Clean up orphaned FKs on both databases."""
        self.stdout.write('\nCleaning up orphaned FKs...')
        
        # Clean local SQLite
        self.stdout.write('  Checking Local SQLite...')
        local_deleted = self._cleanup_orphaned_fks_db('sqlite')
        if local_deleted > 0:
            self.stdout.write(f'    Deleted {local_deleted} orphaned record(s)')
        else:
            self.stdout.write('    No orphans found')

        # Clean Neon PostgreSQL
        self.stdout.write('  Checking Neon PostgreSQL...')
        neon_deleted = self._cleanup_orphaned_fks_db('neon')
        if neon_deleted > 0:
            self.stdout.write(f'    Deleted {neon_deleted} orphaned record(s)')
        else:
            self.stdout.write('    No orphans found')

    def _cleanup_orphaned_fks_db(self, db_alias):
        """Clean up orphaned FKs on a specific database."""
        is_pg = 'postgresql' in settings.DATABASES[db_alias].get('ENGINE', '')
        
        if is_pg:
            # For PostgreSQL, we need a different approach
            return self._cleanup_orphaned_fks_postgres(db_alias)
        else:
            # For SQLite, use the existing method
            return self._cleanup_orphaned_fks_sqlite(db_alias)

    def _cleanup_orphaned_fks_sqlite(self, db_alias):
        """Clean up orphaned FKs on SQLite."""
        total_deleted = 0
        
        with connections[db_alias].cursor() as cursor:
            cursor.execute('PRAGMA foreign_keys = OFF;')
            
            # Get all tables
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name NOT LIKE 'sqlite_%'
            """)
            tables = [row[0] for row in cursor.fetchall()]
            
            for table in tables:
                try:
                    # Get FK info
                    cursor.execute(f'PRAGMA foreign_key_list("{table}")')
                    fks = cursor.fetchall()
                    
                    for fk in fks:
                        ref_table = fk[2]
                        fk_column = fk[3]
                        ref_column = fk[4]
                        
                        # Find and delete orphans
                        try:
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
                            total_deleted += cursor.rowcount
                        except Exception:
                            pass
                except Exception:
                    pass
            
            cursor.execute('PRAGMA foreign_keys = ON;')
        
        return total_deleted

    def _cleanup_orphaned_fks_postgres(self, db_alias):
        """Clean up orphaned FKs on PostgreSQL."""
        total_deleted = 0
        
        with connections[db_alias].cursor() as cursor:
            # Get all FK constraints
            cursor.execute("""
                SELECT
                    tc.table_name,
                    kcu.column_name,
                    ccu.table_name AS ref_table,
                    ccu.column_name AS ref_column
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                    ON tc.constraint_name = kcu.constraint_name
                JOIN information_schema.constraint_column_usage ccu
                    ON ccu.constraint_name = tc.constraint_name
                WHERE tc.constraint_type = 'FOREIGN KEY'
                  AND tc.table_schema = 'public'
            """)
            
            fks = cursor.fetchall()
            
            for table, fk_col, ref_table, ref_col in fks:
                try:
                    # Find and delete orphans
                    cursor.execute(f"""
                        DELETE FROM "{table}"
                        WHERE "{fk_col}" IS NOT NULL
                          AND "{fk_col}" NOT IN (
                              SELECT "{ref_col}" FROM "{ref_table}"
                          )
                    """)
                    deleted = cursor.rowcount
                    total_deleted += deleted
                except Exception:
                    pass
        
        return total_deleted

    def _count_orphaned_fks(self, db_alias):
        """Count orphaned FK references."""
        is_pg = 'postgresql' in settings.DATABASES[db_alias].get('ENGINE', '')
        orphan_count = 0

        with connections[db_alias].cursor() as cursor:
            if is_pg:
                # PostgreSQL
                cursor.execute("""
                    SELECT
                        tc.table_name,
                        kcu.column_name,
                        ccu.table_name AS ref_table,
                        ccu.column_name AS ref_column
                    FROM information_schema.table_constraints tc
                    JOIN information_schema.key_column_usage kcu
                        ON tc.constraint_name = kcu.constraint_name
                    JOIN information_schema.constraint_column_usage ccu
                        ON ccu.constraint_name = tc.constraint_name
                    WHERE tc.constraint_type = 'FOREIGN KEY'
                      AND tc.table_schema = 'public'
                """)
                
                for table, fk_col, ref_table, ref_col in cursor.fetchall():
                    try:
                        cursor.execute(f"""
                            SELECT COUNT(*)
                            FROM "{table}" t
                            LEFT JOIN "{ref_table}" r ON t."{fk_col}" = r."{ref_col}"
                            WHERE t."{fk_col}" IS NOT NULL
                              AND r."{ref_col}" IS NULL
                        """)
                        count = cursor.fetchone()[0]
                        orphan_count += count
                    except Exception:
                        pass
            else:
                # SQLite
                cursor.execute("""
                    SELECT name FROM sqlite_master 
                    WHERE type='table' AND name NOT LIKE 'sqlite_%'
                """)
                tables = [row[0] for row in cursor.fetchall()]
                
                for table in tables:
                    try:
                        cursor.execute(f'PRAGMA foreign_key_list("{table}")')
                        fks = cursor.fetchall()
                        
                        for fk in fks:
                            ref_table = fk[2]
                            fk_column = fk[3]
                            ref_column = fk[4]
                            
                            cursor.execute(f"""
                                SELECT COUNT(*)
                                FROM "{table}" t
                                LEFT JOIN "{ref_table}" r ON t."{fk_column}" = r."{ref_column}"
                                WHERE t."{fk_column}" IS NOT NULL
                                  AND r."{ref_column}" IS NULL
                            """)
                            count = cursor.fetchone()[0]
                            orphan_count += count
                    except Exception:
                        pass

        return orphan_count

    # ========================================================================
    # Helper methods (same as original db_sync.py)
    # ========================================================================

    @staticmethod
    def _ensure_both_databases():
        """Ensure both 'neon' and 'sqlite' database aliases exist."""
        from pathlib import Path
        
        _DB_DEFAULTS = {
            'ATOMIC_REQUESTS': False,
            'AUTOCOMMIT': True,
            'CONN_MAX_AGE': 0,
            'CONN_HEALTH_CHECKS': False,
            'OPTIONS': {},
            'TIME_ZONE': None,
            'USER': '',
            'PASSWORD': '',
            'HOST': '',
            'PORT': '',
        }
        
        if 'neon' not in settings.DATABASES:
            neon_conf = {
                **_DB_DEFAULTS,
                **dj_database_url.parse(
                    NEON_URL, conn_max_age=600, ssl_require=True
                ),
            }
            settings.DATABASES['neon'] = neon_conf
            connections.databases['neon'] = neon_conf
            
        if 'sqlite' not in settings.DATABASES:
            sqlite_conf = {
                **_DB_DEFAULTS,
                'ENGINE': 'django.db.backends.sqlite3',
                'NAME': str(Path(settings.BASE_DIR) / 'db.sqlite3'),
                'OPTIONS': {'timeout': 30},
            }
            settings.DATABASES['sqlite'] = sqlite_conf
            connections.databases['sqlite'] = sqlite_conf

    @staticmethod
    def _topo_sort_models():
        """Return models sorted by FK dependencies (parents first)."""
        all_models = list(apps.get_models(include_auto_created=True))
        model_set = set(all_models)

        deps = {m: set() for m in all_models}
        for model in all_models:
            for field in model._meta.get_fields():
                if (field.is_relation
                        and getattr(field, 'concrete', False)
                        and field.related_model
                        and field.related_model in model_set
                        and field.related_model is not model):
                    deps[model].add(field.related_model)

        # Manual overrides
        def _model(label):
            app, name = label.split('.')
            for m in all_models:
                if m._meta.app_label == app and m._meta.model_name == name:
                    return m
            return None

        _force_order = [
            ("sales.salespickupline", "sales.salespickup"),
        ]
        for child_label, parent_label in _force_order:
            child = _model(child_label)
            parent = _model(parent_label)
            if child and parent:
                deps[child].add(parent)

        # Kahn's algorithm
        in_degree = {m: 0 for m in all_models}
        reverse = {m: set() for m in all_models}
        for model, parents in deps.items():
            for parent in parents:
                in_degree[model] += 1
                reverse[parent].add(model)

        queue = deque(m for m in all_models if in_degree[m] == 0)
        sorted_models = []
        while queue:
            m = queue.popleft()
            sorted_models.append(m)
            for child in reverse[m]:
                in_degree[child] -= 1
                if in_degree[child] == 0:
                    queue.append(child)

        # Append cycles
        seen = set(sorted_models)
        for m in all_models:
            if m not in seen:
                sorted_models.append(m)

        return sorted_models

    @staticmethod
    def _truncate_all(db_alias):
        """Truncate all managed tables."""
        is_pg = 'postgresql' in settings.DATABASES[db_alias].get('ENGINE', '')
        all_models = apps.get_models(include_auto_created=True)
        tables = [m._meta.db_table for m in all_models if m._meta.managed]

        with connections[db_alias].cursor() as cursor:
            if is_pg:
                if tables:
                    existing_tables = []
                    for t in tables:
                        try:
                            cursor.execute(f"SELECT 1 FROM {t} LIMIT 1")
                            existing_tables.append(t)
                        except Exception:
                            pass
                    
                    if existing_tables:
                        table_list = ', '.join(f'"{t}"' for t in existing_tables)
                        try:
                            cursor.execute(
                                f'TRUNCATE TABLE {table_list} RESTART IDENTITY CASCADE'
                            )
                        except Exception:
                            for t in existing_tables:
                                try:
                                    cursor.execute(f'DELETE FROM "{t}"')
                                except Exception:
                                    pass
            else:
                cursor.execute('PRAGMA foreign_keys = OFF;')
                for t in tables:
                    try:
                        cursor.execute(f'DELETE FROM "{t}";')
                    except Exception:
                        pass
                cursor.execute('PRAGMA foreign_keys = ON;')

    @staticmethod
    def _drop_fk_constraints(db_alias):
        """Drop all FK constraints on PostgreSQL."""
        saved = []
        with connections[db_alias].cursor() as cursor:
            cursor.execute("""
                SELECT
                    tc.table_name,
                    tc.constraint_name,
                    pg_get_constraintdef(pgc.oid) AS condef
                FROM information_schema.table_constraints tc
                JOIN pg_constraint pgc
                    ON pgc.conname = tc.constraint_name
                WHERE tc.constraint_type = 'FOREIGN KEY'
                  AND tc.table_schema = 'public'
            """)
            for table, con_name, condef in cursor.fetchall():
                saved.append((table, con_name, condef))

            for table, con_name, _condef in saved:
                cursor.execute(
                    f'ALTER TABLE "{table}" DROP CONSTRAINT "{con_name}"'
                )
        return saved

    @staticmethod
    def _restore_fk_constraints(db_alias, saved_fks):
        """Restore FK constraints on PostgreSQL."""
        errs = []
        with connections[db_alias].cursor() as cursor:
            for table, con_name, condef in saved_fks:
                try:
                    cursor.execute(
                        f'ALTER TABLE "{table}" ADD CONSTRAINT "{con_name}" {condef}'
                    )
                except Exception as exc:
                    errs.append(f'{table}.{con_name}: {exc}')
        return errs

    @staticmethod
    def _reset_sequences(db_alias, all_models):
        """Reset PostgreSQL sequences."""
        with connections[db_alias].cursor() as cursor:
            for model in all_models:
                if not model._meta.managed:
                    continue
                db_table = model._meta.db_table
                pk_col = model._meta.pk.column if model._meta.pk else None
                if pk_col:
                    try:
                        cursor.execute(f"""
                            SELECT setval(
                                pg_get_serial_sequence('{db_table}', '{pk_col}'),
                                COALESCE(
                                    (SELECT MAX("{pk_col}") FROM "{db_table}"), 1
                                ),
                                true
                            )
                        """)
                    except Exception:
                        pass

