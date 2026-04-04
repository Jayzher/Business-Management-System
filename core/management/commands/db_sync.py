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
        call_command('migrate', '--run-syncdb', database=dst,
                     verbosity=0, stdout=self.stdout)
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
        self.stdout.write('=' * 60)

    # -- helpers --------------------------------------------------------------

    @staticmethod
    def _topo_sort_models():
        """Return all models sorted so that FK parents come before children."""
        all_models = apps.get_models(include_auto_created=True)
        model_set = set(all_models)

        # Build adjacency: model -> set of models it depends on via forward FKs
        deps = defaultdict(set)
        for model in all_models:
            for field in model._meta.get_fields():
                # Only consider concrete forward FK fields (not reverse relations)
                if (field.is_relation
                        and getattr(field, 'concrete', False)
                        and field.related_model
                        and field.related_model in model_set
                        and field.related_model is not model):
                    deps[model].add(field.related_model)

        # Kahn's algorithm for topological sort
        in_degree = defaultdict(int)
        reverse = defaultdict(set)
        for model in all_models:
            if model not in in_degree:
                in_degree[model] = 0
            for parent in deps[model]:
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

        # Append any remaining (circular deps) at the end
        seen = set(sorted_models)
        for m in all_models:
            if m not in seen:
                sorted_models.append(m)

        return sorted_models

    @staticmethod
    def _truncate_all(db_alias):
        """
        Truncate every managed table on the destination database.
        Uses TRUNCATE … CASCADE on PostgreSQL, DELETE on SQLite.
        """
        is_pg = 'postgresql' in settings.DATABASES[db_alias].get('ENGINE', '')
        all_models = apps.get_models(include_auto_created=True)
        tables = [m._meta.db_table for m in all_models if m._meta.managed]

        with connections[db_alias].cursor() as cursor:
            if is_pg:
                if tables:
                    table_list = ', '.join(f'"{t}"' for t in tables)
                    cursor.execute(
                        f'TRUNCATE TABLE {table_list} RESTART IDENTITY CASCADE'
                    )
            else:
                cursor.execute('PRAGMA foreign_keys = OFF;')
                for t in tables:
                    cursor.execute(f'DELETE FROM "{t}";')
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
