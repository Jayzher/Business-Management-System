"""
Drain the SyncOutbox: replay pending local writes to Neon.

Usage:
    python manage.py drain_sync_outbox
    python manage.py drain_sync_outbox --batch-size 100
    python manage.py drain_sync_outbox --dry-run

This command reads all PENDING entries from SyncOutbox (stored in local_cache)
and replays them to Neon (default) in chronological order.

On success, entries are marked SYNCED.
On failure, entries are marked FAILED with the error message and retry count.

Designed to be run:
  - Manually from the Tests & Syncs page
  - As a cron job (e.g. every 30 seconds)
  - Automatically when Neon connectivity is restored
"""

from django.apps import apps
from django.core.management.base import BaseCommand
from django.db import connections
from django.utils import timezone


class Command(BaseCommand):
    help = 'Replay pending SyncOutbox entries from local_cache to Neon.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--batch-size',
            type=int,
            default=500,
            help='Max entries to process per run (default: 500).',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be replayed without writing.',
        )
        parser.add_argument(
            '--max-retries',
            type=int,
            default=5,
            help='Skip entries that have failed more than this many times.',
        )

    def handle(self, *args, **options):
        batch_size = options['batch_size']
        dry_run = options['dry_run']
        max_retries = options['max_retries']

        from sync.models import SyncOutbox, SyncOutboxStatus

        # Check Neon connectivity first
        from inventory_system.db_router import force_neon_recheck
        if not force_neon_recheck():
            self.stderr.write(self.style.ERROR(
                'Neon is still unreachable. Cannot drain outbox.'
            ))
            return

        # Fetch pending entries
        pending = list(
            SyncOutbox.objects.using('local_cache')
            .filter(status=SyncOutboxStatus.PENDING, retry_count__lte=max_retries)
            .order_by('created_at')[:batch_size]
        )

        if not pending:
            self.stdout.write('No pending outbox entries. Nothing to drain.')
            return

        self.stdout.write(f'Found {len(pending)} pending outbox entries.')
        if dry_run:
            for entry in pending:
                self.stdout.write(f'  {entry.action} {entry.db_table}#{entry.row_pk}')
            self.stdout.write('(dry run — no changes made)')
            return

        synced = 0
        failed = 0

        for entry in pending:
            try:
                model = apps.get_model(entry.app_label, entry.model_name)

                if entry.action == 'upsert':
                    self._replay_upsert(model, entry)
                elif entry.action == 'delete':
                    self._replay_delete(model, entry)

                # Mark as synced
                entry.status = SyncOutboxStatus.SYNCED
                entry.synced_at = timezone.now()
                entry.save(using='local_cache')
                synced += 1

            except Exception as exc:
                entry.status = SyncOutboxStatus.PENDING  # Keep pending for retry
                entry.retry_count += 1
                entry.error_message = str(exc)[:500]
                if entry.retry_count > max_retries:
                    entry.status = SyncOutboxStatus.FAILED
                    failed += 1
                entry.save(using='local_cache')
                self.stderr.write(
                    self.style.WARNING(
                        f'  RETRY {entry.db_table}#{entry.row_pk}: {exc}'
                    )
                )

        self.stdout.write(self.style.SUCCESS(
            f'Drain complete: {synced} synced, {failed} failed, '
            f'{len(pending) - synced - failed} pending retry.'
        ))

    def _replay_upsert(self, model, entry):
        """Replay an upsert from local_cache → Neon (default)."""
        # Try to read the current row from local_cache
        obj = model._default_manager.using('local_cache').filter(pk=entry.row_pk).first()

        if obj is None:
            # Row was deleted locally after the upsert was queued — skip
            return

        concrete_fields = [
            f for f in model._meta.concrete_fields if not f.primary_key
        ]
        update_fields = [f.attname for f in concrete_fields]

        if update_fields:
            model._default_manager.using('default').bulk_create(
                [obj],
                update_conflicts=True,
                update_fields=update_fields,
                unique_fields=['id'],
            )
        else:
            model._default_manager.using('default').bulk_create(
                [obj], ignore_conflicts=True,
            )

        # Log to NeonChangeLog so other devices can catch up
        from sync.signals import _log_to_neon_changelog, _instance_to_dict
        row_data = _instance_to_dict(obj)
        _log_to_neon_changelog(
            'upsert', entry.db_table, entry.app_label,
            entry.model_name, entry.row_pk, row_data,
        )

    def _replay_delete(self, model, entry):
        """Replay a delete from local_cache → Neon (default)."""
        model._default_manager.using('default').filter(pk=entry.row_pk).delete()

        # Log to NeonChangeLog so other devices can catch up
        from sync.signals import _log_to_neon_changelog
        _log_to_neon_changelog(
            'delete', entry.db_table, entry.app_label,
            entry.model_name, entry.row_pk, None,
        )
