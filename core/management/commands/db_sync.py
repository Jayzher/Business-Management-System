"""
Bidirectional database sync: Local SQLite <-> Neon PostgreSQL.
Usage:
    python manage.py db_sync --direction local_to_neon
    python manage.py db_sync --direction neon_to_local
"""
import os
from collections import defaultdict, deque
from django.core.management.base import BaseCommand
from django.apps import apps
from django.db import connections
from django.conf import settings
import dj_database_url


from django.conf import settings as _settings
NEON_URL = getattr(_settings, 'NEON_URL', (
    'postgresql://neondb_owner:npg_KhjsX3uB0mil'
    '@ep-raspy-hall-a1fl4lfx.ap-southeast-1.aws.neon.tech'
    '/neondb?sslmode=require'
))
BATCH_SIZE = 500


class Command(BaseCommand):
    help = 'Sync data between local SQLite and Neon PostgreSQL in either direction.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--direction',
            type=str,
            required=True,
            choices=['local_to_neon', 'neon_to_local'],
            help='Direction: "local_to_neon" or "neon_to_local"',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be copied without writing.',
        )

    def handle(self, *args, **options):
        direction = options['direction']
        dry_run = options['dry_run']

        self._ensure_both_databases()

        if direction == 'local_to_neon':
            src, dst = 'sqlite', 'neon'
            label_src, label_dst = 'Local SQLite', 'Neon PostgreSQL'
        else:
            src, dst = 'neon', 'sqlite'
            label_src, label_dst = 'Neon PostgreSQL', 'Local SQLite'

        self.stdout.write('=' * 60)
        self.stdout.write(f'DB Sync: {label_src}  -->  {label_dst}')
        if dry_run:
            self.stdout.write('*** DRY RUN — no data will be written ***')
        self.stdout.write('=' * 60)
        
        # -- Ensure source has latest migrations -------------------------
        self.stdout.write(f'\nEnsuring {label_src} has latest migrations...')
        from django.core.management import call_command
        try:
            call_command('migrate', '--run-syncdb', database=src,
                         verbosity=0, stdout=self.stdout, interactive=False)
            self.stdout.write('  Source migrations up to date.')
        except Exception as e:
            self.stdout.write(self.style.WARNING(f'  Source migration warning: {e}'))

        # -- Topologically sort models by FK deps (parents first) -------------
        all_models = self._topo_sort_models()

        # -- Count source rows -----------------------------------------------
        self.stdout.write(f'\nCounting rows on {label_src}...')
        total_src = 0
        model_counts = []
        for model in all_models:
            name = f'{model._meta.app_label}.{model._meta.model_name}'
            try:
                cnt = model.objects.using(src).count()
            except Exception:
                cnt = 0
            if cnt:
                model_counts.append((model, name, cnt))
                total_src += cnt

        self.stdout.write(f'Source has {total_src} rows across {len(model_counts)} non-empty tables.\n')

        if dry_run:
            for _m, name, cnt in model_counts:
                self.stdout.write(f'  {name}: {cnt} rows')
            self.stdout.write(f'\nTotal: {total_src} rows would be copied.')
            return

        # -- Flush destination ------------------------------------------------
        self.stdout.write(f'Step 1/5: Migrating & flushing {label_dst}...')
        from django.core.management import call_command
        
        # Ensure all tables exist on the destination before flushing
        # Run migrations with --run-syncdb to create any missing tables
        self.stdout.write('  Running migrations on destination...')
        try:
            call_command('migrate', '--run-syncdb', database=dst,
                         verbosity=0, stdout=self.stdout, interactive=False)
        except Exception as e:
            self.stdout.write(self.style.WARNING(f'  Migration warning: {e}'))
        
        # Clean up any orphaned FKs on destination before sync
        self.stdout.write('  Cleaning orphaned FKs on destination...')
        try:
            deleted = self._cleanup_orphaned_fks(dst)
            if deleted > 0:
                self.stdout.write(f'  Cleaned {deleted} orphaned FK(s)')
        except Exception as e:
            self.stdout.write(self.style.WARNING(f'  Cleanup warning: {e}'))
        
        self._truncate_all(dst)
        self.stdout.write('Flushed.\n')

        # -- Disable FK constraints on destination ----------------------------
        dst_is_pg = 'postgresql' in settings.DATABASES[dst].get('ENGINE', '')
        saved_fks = []
        if dst_is_pg:
            self.stdout.write('Step 2/5: Dropping FK constraints on PostgreSQL...')
            saved_fks = self._drop_fk_constraints(dst)
            self.stdout.write(f'Dropped {len(saved_fks)} FK constraints.\n')
        else:
            self.stdout.write('Step 2/5: Disabling FK checks on SQLite...')
            with connections[dst].cursor() as cursor:
                cursor.execute('PRAGMA foreign_keys = OFF;')
            self.stdout.write('FK checks disabled.\n')

        # -- Copy data --------------------------------------------------------
        self.stdout.write(f'Step 3/5: Copying data {label_src} -> {label_dst}')
        total_copied = 0
        errors = []

        for model, name, cnt in model_counts:
            try:
                objs = list(model.objects.using(src).all())
                for obj in objs:
                    obj._state.adding = True
                    obj._state.db = dst

                for i in range(0, len(objs), BATCH_SIZE):
                    batch = objs[i:i + BATCH_SIZE]
                    model.objects.using(dst).bulk_create(
                        batch, batch_size=BATCH_SIZE, ignore_conflicts=True,
                    )
                total_copied += cnt
                self.stdout.write(f'  OK    {name}: {cnt} rows')
            except Exception as exc:
                msg = f'  ERROR {name}: {exc}'
                self.stdout.write(msg)
                errors.append(msg)

        # -- Re-enable FK constraints ----------------------------------------
        if dst_is_pg and saved_fks:
            self.stdout.write(f'\nStep 4/5: Restoring {len(saved_fks)} FK constraints...')
            restore_errors = self._restore_fk_constraints(dst, saved_fks)
            if restore_errors:
                self.stdout.write(f'{len(restore_errors)} FK constraints could not be restored:')
                for e in restore_errors:
                    self.stdout.write(f'  WARN  {e}')
            else:
                self.stdout.write('All FK constraints restored.')
        elif not dst_is_pg:
            with connections[dst].cursor() as cursor:
                cursor.execute('PRAGMA foreign_keys = ON;')
            self.stdout.write('\nStep 4/5: FK checks re-enabled.')
        else:
            self.stdout.write('\nStep 4/5: (no FK constraints to restore)')

        # -- Reset sequences (PostgreSQL only) --------------------------------
        pg_alias = 'neon' if direction == 'local_to_neon' else None
        if pg_alias:
            self.stdout.write(f'\nStep 5/5: Resetting PostgreSQL sequences...')
            with connections[pg_alias].cursor() as cursor:
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
            self.stdout.write('Sequences reset.')
        else:
            self.stdout.write(f'\nStep 5/5: (SQLite target — no sequence reset needed)')

        # -- Summary ----------------------------------------------------------
        self.stdout.write('\n' + '=' * 60)
        self.stdout.write(f'Sync complete! {total_copied} total rows copied.')
        if errors:
            self.stdout.write(f'{len(errors)} errors:')
            for e in errors:
                self.stdout.write(e)
        else:
            self.stdout.write('No errors!')
        
        # -- Post-sync validation -----------------------------------------
        self.stdout.write('\nValidating FK integrity...')
        orphans_found = self._validate_fk_integrity(dst)
        if orphans_found > 0:
            self.stdout.write(self.style.WARNING(
                f'  WARNING: {orphans_found} orphaned FK(s) found after sync!'
            ))
            self.stdout.write('  Run: python manage.py cleanup_orphaned_fks')
        else:
            self.stdout.write('  FK integrity OK')
        
        self.stdout.write('=' * 60)

    # -- helpers --------------------------------------------------------------

    @staticmethod
    def _topo_sort_models():
        """Return all models sorted so that FK parents come before children.

        Uses Kahn's algorithm on a deduplicated dependency graph so that
        in-degree counts are exact and no node is enqueued twice.
        Manual overrides cover tables whose FK edges are not visible via
        Django's _meta (e.g. through abstract base classes or GenericFKs).
        """
        all_models = list(apps.get_models(include_auto_created=True))
        model_set = set(all_models)

        # ── 1. Build deps: model → {models it must come AFTER} ──────────────
        # Use sets throughout so duplicate FK edges don't inflate in-degree.
        deps: dict[object, set] = {m: set() for m in all_models}
        for model in all_models:
            for field in model._meta.get_fields():
                if (field.is_relation
                        and getattr(field, 'concrete', False)
                        and field.related_model
                        and field.related_model in model_set
                        and field.related_model is not model):
                    deps[model].add(field.related_model)

        # ── 2. Manual overrides for known-problematic tables ─────────────────
        def _model(label):
            app, name = label.split('.')
            for m in all_models:
                if m._meta.app_label == app and m._meta.model_name == name:
                    return m
            return None

        # SalesPickupLine.pickup → SalesPickup  (CASCADE FK)
        _force_order = [
            ("sales.salespickupline",  "sales.salespickup"),
            # add more ("child", "parent") pairs here if needed
        ]
        for child_label, parent_label in _force_order:
            child  = _model(child_label)
            parent = _model(parent_label)
            if child and parent:
                deps[child].add(parent)

        # ── 3. Build reverse graph and exact in-degree from deduplicated deps ─
        in_degree: dict[object, int] = {m: 0 for m in all_models}
        reverse:   dict[object, set] = {m: set() for m in all_models}
        for model, parents in deps.items():
            for parent in parents:
                in_degree[model] += 1      # counted once per unique parent
                reverse[parent].add(model)

        # ── 4. Kahn's BFS ────────────────────────────────────────────────────
        queue = deque(m for m in all_models if in_degree[m] == 0)
        sorted_models: list = []
        while queue:
            m = queue.popleft()
            sorted_models.append(m)
            for child in reverse[m]:
                in_degree[child] -= 1
                if in_degree[child] == 0:
                    queue.append(child)

        # ── 5. Append anything left (genuine cycles) at the end ──────────────
        seen = set(sorted_models)
        for m in all_models:
            if m not in seen:
                sorted_models.append(m)

        # ── 6. Debug log ─────────────────────────────────────────────────────
        import sys
        print("Model copy order:", file=sys.stderr)
        for m in sorted_models:
            print(f"  {m._meta.app_label}.{m._meta.model_name}", file=sys.stderr)

        return sorted_models

    @staticmethod
    def _truncate_all(db_alias):
        """
        Truncate every managed table on the destination database.
        Uses TRUNCATE … CASCADE on PostgreSQL, DELETE on SQLite.
        Skips tables that don't exist.
        """
        is_pg = 'postgresql' in settings.DATABASES[db_alias].get('ENGINE', '')
        all_models = apps.get_models(include_auto_created=True)
        tables = [m._meta.db_table for m in all_models if m._meta.managed]

        with connections[db_alias].cursor() as cursor:
            if is_pg:
                if tables:
                    # For PostgreSQL, check which tables exist first
                    existing_tables = []
                    for t in tables:
                        try:
                            cursor.execute(f"SELECT 1 FROM {t} LIMIT 1")
                            existing_tables.append(t)
                        except Exception:
                            pass  # Table doesn't exist, skip it
                    
                    if existing_tables:
                        table_list = ', '.join(f'"{t}"' for t in existing_tables)
                        try:
                            cursor.execute(
                                f'TRUNCATE TABLE {table_list} RESTART IDENTITY CASCADE'
                            )
                        except Exception:
                            # If truncate fails, try deleting from each table individually
                            for t in existing_tables:
                                try:
                                    cursor.execute(f'DELETE FROM "{t}"')
                                except Exception:
                                    pass
            else:
                # SQLite
                cursor.execute('PRAGMA foreign_keys = OFF;')
                for t in tables:
                    try:
                        cursor.execute(f'DELETE FROM "{t}";')
                    except Exception:
                        pass  # Table doesn't exist or error, skip it
                cursor.execute('PRAGMA foreign_keys = ON;')

    @staticmethod
    def _drop_fk_constraints(db_alias):
        """
        Drop all FK constraints on a PostgreSQL database.
        Returns list of (table, constraint_name, definition) for later restore.
        """
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
        """Re-add saved FK constraints. Returns list of error messages."""
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
    def _cleanup_orphaned_fks(db_alias):
        """Remove orphaned FK references before sync. Returns count of deleted records."""
        total_deleted = 0
        
        # Check if this is SQLite (only SQLite supports PRAGMA)
        is_sqlite = 'sqlite' in settings.DATABASES[db_alias].get('ENGINE', '')
        if not is_sqlite:
            return 0  # Skip for non-SQLite databases
        
        with connections[db_alias].cursor() as cursor:
            # Get all tables
            try:
                cursor.execute("""
                    SELECT name FROM sqlite_master 
                    WHERE type='table' AND name NOT LIKE 'sqlite_%'
                """)
                tables = [row[0] for row in cursor.fetchall()]
            except Exception:
                return 0
            
            for table in tables:
                try:
                    # Check if table exists first
                    cursor.execute(f"""
                        SELECT name FROM sqlite_master 
                        WHERE type='table' AND name='{table}'
                    """)
                    if not cursor.fetchone():
                        continue
                    
                    # Get FK info
                    cursor.execute(f'PRAGMA foreign_key_list("{table}")')
                    fks = cursor.fetchall()
                    
                    for fk in fks:
                        ref_table = fk[2]
                        fk_column = fk[3]
                        ref_column = fk[4]
                        
                        # Check if referenced table exists
                        cursor.execute(f"""
                            SELECT name FROM sqlite_master 
                            WHERE type='table' AND name='{ref_table}'
                        """)
                        if not cursor.fetchone():
                            continue  # Skip if referenced table doesn't exist
                        
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
                            pass  # Skip if query fails
                except Exception:
                    pass  # Skip table if any error
        
        return total_deleted

    @staticmethod
    def _validate_fk_integrity(db_alias):
        """Check for orphaned FK references after sync."""
        orphan_count = 0
        with connections[db_alias].cursor() as cursor:
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name NOT LIKE 'sqlite_%'
            """)
            tables = [row[0] for row in cursor.fetchall()]
            
            for table in tables:
                cursor.execute(f'PRAGMA foreign_key_list("{table}")')
                fks = cursor.fetchall()
                
                for fk in fks:
                    ref_table = fk[2]
                    fk_column = fk[3]
                    ref_column = fk[4]
                    
                    try:
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

    @staticmethod
    def _ensure_both_databases():
        """
        Make sure Django knows about both 'sqlite' and 'neon' database aliases
        regardless of the current DATABASE_URL setting.
        """
        from django.db import connections

        base_dir = settings.BASE_DIR

        _DB_DEFAULTS = {
            'ATOMIC_REQUESTS': False,
            'AUTOCOMMIT': True,
            'CONN_MAX_AGE': 0,
            'CONN_HEALTH_CHECKS': False,
            'OPTIONS': {},
            'TIME_ZONE': None,
            'TEST': {
                'CHARSET': None,
                'COLLATION': None,
                'MIGRATE': True,
                'MIRROR': None,
                'NAME': None,
            },
        }

        if 'sqlite' not in settings.DATABASES:
            sqlite_conf = {
                **_DB_DEFAULTS,
                'ENGINE': 'django.db.backends.sqlite3',
                'NAME': str(base_dir / 'db.sqlite3'),
                'USER': '',
                'PASSWORD': '',
                'HOST': '',
                'PORT': '',
            }
            settings.DATABASES['sqlite'] = sqlite_conf
            connections.databases['sqlite'] = sqlite_conf

        if 'neon' not in settings.DATABASES:
            neon_conf = {
                **_DB_DEFAULTS,
                **dj_database_url.parse(
                    NEON_URL, conn_max_age=600, ssl_require=True,
                ),
            }
            settings.DATABASES['neon'] = neon_conf
            connections.databases['neon'] = neon_conf
