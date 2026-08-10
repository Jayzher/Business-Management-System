"""
Reconcile local_cache with Neon — handles pre-existing changes.

This command is designed to run ONCE after deploying the new changelog-based
sync system.  It handles all changes that were made to Neon BEFORE the
NeonChangeLog was in place — i.e., changes that were never logged and
therefore can't be caught by the normal delta sync.

What it does:
  1. For every synced model, compares Neon (source of truth) vs local_cache.
  2. Finds rows that:
     a) Exist on Neon but NOT in local_cache → inserts them locally
     b) Exist on Neon AND local_cache but differ → updates local_cache
     c) Exist in local_cache but NOT on Neon → deletes from local_cache
  3. After reconciliation, sets the changelog checkpoint to the latest
     NeonChangeLog entry (so future syncs only pull the delta).

When to run:
  - ONCE after deploying the changelog sync system for the first time.
  - After a suspected data drift (e.g., direct SQL on Neon that bypassed Django).
  - As a periodic health check (e.g., weekly cron) to catch any drift.

Usage:
    python manage.py reconcile_local_cache
    python manage.py reconcile_local_cache --dry-run
    python manage.py reconcile_local_cache --tables catalog_item,inventory_stockbalance
    python manage.py reconcile_local_cache --backfill-changelog
"""

import time
from django.apps import apps
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connections


BATCH_SIZE = 500


class Command(BaseCommand):
    help = (
        'Reconcile local_cache (SQLite) with Neon (PostgreSQL). '
        'Fixes all discrepancies caused by changes made before the '
        'changelog sync system was deployed.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would change without writing.',
        )
        parser.add_argument(
            '--tables',
            type=str,
            default='',
            help='Comma-separated list of db_table names to reconcile (default: all).',
        )
        parser.add_argument(
            '--backfill-changelog',
            action='store_true',
            help=(
                'After reconciling, backfill NeonChangeLog with an entry for '
                'every row currently on Neon. This ensures the changelog has a '
                'complete baseline for future delta syncs on other devices.'
            ),
        )
        parser.add_argument(
            '--quiet', '-q',
            action='store_true',
            help='Suppress per-row output.',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        table_filter = [t.strip() for t in options['tables'].split(',') if t.strip()]
        backfill = options['backfill_changelog']
        self.quiet = options['quiet']

        sync_mode = getattr(settings, 'SYNC_MODE', 'offline')
        if sync_mode == 'offline':
            self.stdout.write(self.style.WARNING(
                'SYNC_MODE is "offline" — nothing to reconcile.'
            ))
            return

        from sync.signals import SYNCED_APP_LABELS, set_sync_in_progress
        from sync.background_sync import pause_worker, resume_worker

        # Set sync-in-progress to prevent signal handlers from interfering
        set_sync_in_progress(True)
        # Pause the background sync worker too — without this, it fights
        # this command for SQLite's single write lock on every batch,
        # surfacing as "database is locked" errors mid-reconcile.
        pause_worker()

        try:
            self.stdout.write('=' * 60)
            mode = 'DRY-RUN' if dry_run else 'RECONCILING'
            self.stdout.write(f'  Reconcile local_cache with Neon [{mode}]')
            self.stdout.write('=' * 60)

            # Get all synced models
            all_models = [
                m for m in apps.get_models()
                if m._meta.app_label in SYNCED_APP_LABELS and m._meta.managed
            ]

            if table_filter:
                all_models = [m for m in all_models if m._meta.db_table in table_filter]

            start = time.time()
            total_inserted = 0
            total_updated = 0
            total_deleted = 0
            total_unchanged = 0
            errors = []

            # Disable FK checks on SQLite for bulk operations
            with connections['local_cache'].cursor() as cursor:
                cursor.execute('PRAGMA foreign_keys = OFF;')

            for model in all_models:
                try:
                    stats = self._reconcile_model(model, dry_run)
                    total_inserted += stats['inserted']
                    total_updated += stats['updated']
                    total_deleted += stats['deleted']
                    total_unchanged += stats['unchanged']

                    if stats['inserted'] or stats['updated'] or stats['deleted']:
                        self._info(
                            f'  {model._meta.db_table:<40} '
                            f'+{stats["inserted"]} ~{stats["updated"]} '
                            f'-{stats["deleted"]} ={stats["unchanged"]}'
                        )
                except Exception as exc:
                    msg = f'  ERROR {model._meta.db_table}: {exc}'
                    self.stdout.write(self.style.ERROR(msg))
                    errors.append(msg)

            # Re-enable FK checks
            with connections['local_cache'].cursor() as cursor:
                cursor.execute('PRAGMA foreign_keys = ON;')

            elapsed = time.time() - start

            self.stdout.write('')
            self.stdout.write('=' * 60)
            self.stdout.write(f'  Reconciliation complete in {elapsed:.1f}s')
            self.stdout.write(f'  Inserted: {total_inserted}')
            self.stdout.write(f'  Updated:  {total_updated}')
            self.stdout.write(f'  Deleted:  {total_deleted}')
            self.stdout.write(f'  Unchanged: {total_unchanged}')
            if errors:
                self.stdout.write(f'  Errors:   {len(errors)}')
            self.stdout.write('=' * 60)

            # Set the checkpoint to latest after reconciliation
            if not dry_run:
                from sync.startup_sync import _set_checkpoint_to_latest, _set_last_sync_time
                from django.utils import timezone
                _set_checkpoint_to_latest()
                _set_last_sync_time(timezone.now())
                self.stdout.write(self.style.SUCCESS(
                    '  Checkpoint set to latest. Future syncs will use changelog delta.'
                ))

            # Optionally backfill the changelog
            if backfill and not dry_run:
                self.stdout.write('')
                self._backfill_changelog(all_models)

        finally:
            resume_worker()
            set_sync_in_progress(False)

    def _reconcile_model(self, model, dry_run) -> dict:
        """
        Compare all rows of a model between Neon and local_cache.
        Returns stats dict with inserted/updated/deleted/unchanged counts.
        """
        stats = {'inserted': 0, 'updated': 0, 'deleted': 0, 'unchanged': 0}

        # Get all PKs and updated_at from both databases
        neon_data = self._get_row_fingerprints(model, 'default')
        local_data = self._get_row_fingerprints(model, 'local_cache')

        neon_pks = set(neon_data.keys())
        local_pks = set(local_data.keys())

        # Rows on Neon but not in local_cache → INSERT
        missing_pks = neon_pks - local_pks

        # Rows in local_cache but not on Neon → DELETE (orphans)
        orphan_pks = local_pks - neon_pks

        # Rows in both → check if they differ (by updated_at timestamp)
        common_pks = neon_pks & local_pks
        stale_pks = []
        for pk in common_pks:
            neon_ts = neon_data[pk]
            local_ts = local_data[pk]
            if neon_ts != local_ts:
                stale_pks.append(pk)
            else:
                stats['unchanged'] += 1

        # Apply changes
        if not dry_run:
            # INSERT missing rows
            if missing_pks:
                self._bulk_copy_from_neon(model, list(missing_pks))
            stats['inserted'] = len(missing_pks)

            # UPDATE stale rows
            if stale_pks:
                self._bulk_copy_from_neon(model, stale_pks)
            stats['updated'] = len(stale_pks)

            # DELETE orphan rows
            if orphan_pks:
                model._default_manager.using('local_cache').filter(
                    pk__in=list(orphan_pks)
                ).delete()
            stats['deleted'] = len(orphan_pks)
        else:
            stats['inserted'] = len(missing_pks)
            stats['updated'] = len(stale_pks)
            stats['deleted'] = len(orphan_pks)

        return stats

    def _get_row_fingerprints(self, model, db_alias) -> dict:
        """
        Get a dict of {pk: updated_at_str} for all rows of a model on a DB.
        If the model has no updated_at, uses created_at.
        If neither exists, uses just the PK (presence check only).
        """
        try:
            if hasattr(model, 'updated_at'):
                rows = (
                    model._default_manager.using(db_alias)
                    .values_list('pk', 'updated_at')
                )
                return {pk: str(ts) for pk, ts in rows}
            elif hasattr(model, 'created_at'):
                rows = (
                    model._default_manager.using(db_alias)
                    .values_list('pk', 'created_at')
                )
                return {pk: str(ts) for pk, ts in rows}
            else:
                # No timestamp — can only detect presence/absence
                pks = model._default_manager.using(db_alias).values_list('pk', flat=True)
                return {pk: '' for pk in pks}
        except Exception:
            return {}

    def _bulk_copy_from_neon(self, model, pks: list):
        """Copy specific rows from Neon → local_cache (upsert)."""
        # Temporarily disable auto_now/auto_now_add
        auto_fields = []
        for field in model._meta.get_fields():
            if hasattr(field, 'auto_now') and field.auto_now:
                field.auto_now = False
                auto_fields.append(('auto_now', field))
            if hasattr(field, 'auto_now_add') and field.auto_now_add:
                field.auto_now_add = False
                auto_fields.append(('auto_now_add', field))

        try:
            concrete_fields = [
                f for f in model._meta.concrete_fields if not f.primary_key
            ]
            update_fields = [f.attname for f in concrete_fields]

            for i in range(0, len(pks), BATCH_SIZE):
                batch_pks = pks[i:i + BATCH_SIZE]
                objs = list(
                    model._default_manager.using('default').filter(pk__in=batch_pks)
                )
                if not objs:
                    continue

                for obj in objs:
                    obj._state.adding = True
                    obj._state.db = 'local_cache'

                if update_fields:
                    model._default_manager.using('local_cache').bulk_create(
                        objs,
                        batch_size=BATCH_SIZE,
                        update_conflicts=True,
                        update_fields=update_fields,
                        unique_fields=['id'],
                    )
                else:
                    model._default_manager.using('local_cache').bulk_create(
                        objs,
                        batch_size=BATCH_SIZE,
                        ignore_conflicts=True,
                    )
        finally:
            for attr, field in auto_fields:
                setattr(field, attr, True)

    def _backfill_changelog(self, models):
        """
        Backfill NeonChangeLog with one 'upsert' entry per row on Neon.
        This creates a complete baseline so other devices that connect later
        can use the changelog to sync without needing a full hydration.
        """
        from sync.models import NeonChangeLog
        from sync.signals import _instance_to_dict, _get_device_id

        self.stdout.write('Backfilling NeonChangeLog...')
        device_id = _get_device_id()
        total = 0

        for model in models:
            table = model._meta.db_table
            app_label = model._meta.app_label
            model_name = model._meta.model_name

            try:
                count = model._default_manager.using('default').count()
                if count == 0:
                    continue

                # Process in batches
                all_pks = list(
                    model._default_manager.using('default')
                    .values_list('pk', flat=True)
                    .order_by('pk')
                )

                for i in range(0, len(all_pks), BATCH_SIZE):
                    batch_pks = all_pks[i:i + BATCH_SIZE]
                    objs = list(
                        model._default_manager.using('default')
                        .filter(pk__in=batch_pks)
                    )

                    changelog_entries = []
                    for obj in objs:
                        row_data = _instance_to_dict(obj)
                        changelog_entries.append(
                            NeonChangeLog(
                                action='upsert',
                                db_table=table,
                                app_label=app_label,
                                model_name=model_name,
                                row_pk=obj.pk,
                                row_data=row_data,
                                source_device=device_id,
                            )
                        )

                    if changelog_entries:
                        NeonChangeLog.objects.using('default').bulk_create(
                            changelog_entries, batch_size=BATCH_SIZE,
                        )
                        total += len(changelog_entries)

                self._info(f'  {table}: {count} entries')

            except Exception as exc:
                self.stdout.write(self.style.ERROR(
                    f'  ERROR backfilling {table}: {exc}'
                ))

        self.stdout.write(self.style.SUCCESS(
            f'  Backfilled {total} changelog entries.'
        ))

        # Update checkpoint to the latest entry
        from sync.startup_sync import _set_checkpoint_to_latest
        _set_checkpoint_to_latest()

    def _info(self, msg):
        if not self.quiet:
            self.stdout.write(msg)
