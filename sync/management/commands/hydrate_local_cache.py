"""
Hydrate local_cache (SQLite) from default (Neon).

Usage:
    python manage.py hydrate_local_cache
    python manage.py hydrate_local_cache --dry-run

This is the bootstrap command for the Neon-primary architecture.
Run it once after switching to SYNC_MODE='neon_primary' to populate
the local SQLite cache from Neon.  After that, the signal layer keeps
local_cache in sync on every write.

Also useful as a periodic reconciliation tool (e.g. cron every 5 min)
to catch any drift caused by direct Neon writes that bypass Django
(admin SQL, migrations, external scripts).
"""

import time
from django.apps import apps
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connections


BATCH_SIZE = 500


class Command(BaseCommand):
    help = 'Hydrate local_cache (SQLite) from default (Neon PostgreSQL).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be copied without writing.',
        )
        parser.add_argument(
            '--tables',
            type=str,
            default='',
            help='Comma-separated list of db_table names to sync (default: all).',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        table_filter = [t.strip() for t in options['tables'].split(',') if t.strip()]

        sync_mode = getattr(settings, 'SYNC_MODE', 'offline')
        if sync_mode == 'offline':
            self.stdout.write(self.style.WARNING(
                'SYNC_MODE is "offline" — default and local_cache are the same DB.\n'
                'Nothing to hydrate. Set DATABASE_URL to a Neon URL to enable.'
            ))
            return

        # Ensure local_cache alias exists
        if 'local_cache' not in settings.DATABASES:
            self.stderr.write('ERROR: local_cache database alias not configured.')
            return

        self.stdout.write('=' * 60)
        self.stdout.write('Hydrating local_cache from default (Neon)')
        if dry_run:
            self.stdout.write('*** DRY RUN — no data will be written ***')
        self.stdout.write('=' * 60)

        # Run migrations on local_cache first
        self.stdout.write('\nEnsuring local_cache schema is up to date...')
        from django.core.management import call_command
        try:
            call_command('migrate', '--run-syncdb', database='local_cache',
                         verbosity=0, interactive=False)
            self.stdout.write('  Migrations applied.')
        except Exception as e:
            self.stdout.write(self.style.WARNING(f'  Migration warning: {e}'))

        # Get all managed models
        from core.management.commands.db_sync import Command as DbSyncCmd
        all_models = DbSyncCmd._topo_sort_models()

        # Filter to synced app labels
        synced_labels = {
            'core', 'accounts', 'catalog', 'partners', 'warehouses',
            'inventory', 'procurement', 'sales', 'audit', 'pricing',
            'pos', 'services', 'cashflow',
        }
        models = [m for m in all_models if m._meta.app_label in synced_labels]

        if table_filter:
            models = [m for m in models if m._meta.db_table in table_filter]

        total_copied = 0
        errors = []
        start = time.time()

        # Disable FK checks on SQLite for bulk load
        with connections['local_cache'].cursor() as cursor:
            cursor.execute('PRAGMA foreign_keys = OFF;')

        for model in models:
            table = model._meta.db_table
            name = f'{model._meta.app_label}.{model._meta.model_name}'

            try:
                count = model._default_manager.using('default').count()
                if count == 0:
                    continue

                if dry_run:
                    self.stdout.write(f'  {name} ({table}): {count} rows')
                    total_copied += count
                    continue

                # Clear local_cache table
                with connections['local_cache'].cursor() as cursor:
                    cursor.execute(f'DELETE FROM "{table}";')

                # Temporarily disable auto_now and auto_now_add so timestamps
                # are preserved from the source (Neon) during the copy.
                auto_fields = []
                for field in model._meta.get_fields():
                    if hasattr(field, 'auto_now') and field.auto_now:
                        field.auto_now = False
                        auto_fields.append(('auto_now', field))
                    if hasattr(field, 'auto_now_add') and field.auto_now_add:
                        field.auto_now_add = False
                        auto_fields.append(('auto_now_add', field))

                try:
                    # Copy in batches
                    objs = list(model._default_manager.using('default').all())
                    for obj in objs:
                        obj._state.adding = True
                        obj._state.db = 'local_cache'

                    # Get all concrete field names for upsert
                    concrete_fields = [
                        f for f in model._meta.concrete_fields if not f.primary_key
                    ]
                    update_fields = [f.attname for f in concrete_fields]

                    for i in range(0, len(objs), BATCH_SIZE):
                        batch = objs[i:i + BATCH_SIZE]
                        if update_fields:
                            model._default_manager.using('local_cache').bulk_create(
                                batch, batch_size=BATCH_SIZE,
                                update_conflicts=True,
                                update_fields=update_fields,
                                unique_fields=['id'],
                            )
                        else:
                            model._default_manager.using('local_cache').bulk_create(
                                batch, batch_size=BATCH_SIZE, ignore_conflicts=True,
                            )
                finally:
                    # Restore auto_now / auto_now_add
                    for attr, field in auto_fields:
                        setattr(field, attr, True)

                total_copied += count
                self.stdout.write(f'  OK    {name}: {count} rows')
            except Exception as exc:
                msg = f'  ERROR {name}: {exc}'
                self.stdout.write(self.style.ERROR(msg))
                errors.append(msg)

        # Re-enable FK checks
        with connections['local_cache'].cursor() as cursor:
            cursor.execute('PRAGMA foreign_keys = ON;')

        elapsed = time.time() - start
        self.stdout.write('\n' + '=' * 60)
        self.stdout.write(f'Done! {total_copied} rows {"would be" if dry_run else ""} copied in {elapsed:.1f}s.')
        if errors:
            self.stdout.write(f'{len(errors)} errors:')
            for e in errors:
                self.stdout.write(e)
        self.stdout.write('=' * 60)
