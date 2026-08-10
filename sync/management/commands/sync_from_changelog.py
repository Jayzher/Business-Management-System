"""
Sync local_cache from Neon's NeonChangeLog.

Usage:
    python manage.py sync_from_changelog
    python manage.py sync_from_changelog --reset
    python manage.py sync_from_changelog --status

This command reads the last-synced changelog ID from local_cache and
fetches all newer entries from Neon, applying them to local_cache.

Options:
  --reset   Clear the checkpoint and do a full hydration from Neon.
  --status  Show the current sync status without making changes.
"""

from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = 'Sync local_cache from Neon using the NeonChangeLog (delta sync).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset',
            action='store_true',
            help='Clear checkpoint and do a full hydration.',
        )
        parser.add_argument(
            '--status',
            action='store_true',
            help='Show current sync status without making changes.',
        )

    def handle(self, *args, **options):
        from django.conf import settings
        from sync.startup_sync import (
            _get_last_synced_log_id,
            _set_last_synced_log_id,
            _replay_changelog_entries,
            _run_full_hydration,
            _set_checkpoint_to_latest,
            _get_last_sync_time,
        )

        sync_mode = getattr(settings, 'SYNC_MODE', 'offline')
        if sync_mode == 'offline':
            self.stdout.write(self.style.WARNING(
                'SYNC_MODE is "offline" — nothing to sync.'
            ))
            return

        if options['status']:
            self._show_status()
            return

        # Pause the background sync worker and flag sync-in-progress for the
        # duration of the actual local_cache write — the same two guards the
        # automatic startup changelog thread uses (sync/startup_sync.py).
        # Without them, this command fights the worker thread and live
        # signal handlers for SQLite's single write lock, surfacing as
        # "database is locked" errors mid-sync.
        from sync.background_sync import pause_worker, resume_worker
        from sync.signals import set_sync_in_progress

        pause_worker()
        set_sync_in_progress(True)
        try:
            if options['reset']:
                self.stdout.write('Resetting checkpoint and running full hydration...')
                _set_last_synced_log_id(0)
                failed = _run_full_hydration()
                if failed:
                    self.stdout.write(self.style.ERROR(
                        f'Full hydration incomplete — {len(failed)} model(s) failed: '
                        f'{", ".join(failed)}. Checkpoint left unset; re-run this command.'
                    ))
                    return
                _set_checkpoint_to_latest()
                self.stdout.write(self.style.SUCCESS('Full hydration complete.'))
                return

            # Normal delta sync
            last_log_id = _get_last_synced_log_id()

            if last_log_id is None:
                self.stdout.write(
                    'No checkpoint found. Running full hydration first...'
                )
                failed = _run_full_hydration()
                if failed:
                    self.stdout.write(self.style.ERROR(
                        f'Full hydration incomplete — {len(failed)} model(s) failed: '
                        f'{", ".join(failed)}. Checkpoint left unset; re-run this command.'
                    ))
                    return
                _set_checkpoint_to_latest()
                self.stdout.write(self.style.SUCCESS('Full hydration complete.'))
                return

            self.stdout.write(f'Last synced changelog ID: {last_log_id}')
            self.stdout.write('Fetching changes from Neon...')

            start = timezone.now()
            applied = _replay_changelog_entries(last_log_id)
            elapsed = (timezone.now() - start).total_seconds()

            new_checkpoint = _get_last_synced_log_id()
            self.stdout.write(self.style.SUCCESS(
                f'Done! Applied {applied} changes in {elapsed:.1f}s. '
                f'Checkpoint: {last_log_id} → {new_checkpoint}'
            ))
        finally:
            set_sync_in_progress(False)
            resume_worker()

        if applied > 0:
            try:
                from sync.signals import broadcast_table_changed
                broadcast_table_changed(['*'])
                self.stdout.write('  Broadcast sent to connected clients.')
            except Exception:
                pass

    def _show_status(self):
        """Display current sync status."""
        from sync.startup_sync import _get_last_synced_log_id, _get_last_sync_time
        from sync.models import NeonChangeLog

        last_log_id = _get_last_synced_log_id()
        last_sync_time = _get_last_sync_time()

        self.stdout.write('═' * 50)
        self.stdout.write('  Sync Status')
        self.stdout.write('═' * 50)

        if last_log_id is not None:
            self.stdout.write(f'  Last synced changelog ID: {last_log_id}')
        else:
            self.stdout.write('  Last synced changelog ID: (none — never synced)')

        if last_sync_time:
            self.stdout.write(f'  Last sync time (legacy):  {last_sync_time.isoformat()}')

        # Check how many entries are pending
        try:
            if last_log_id is not None:
                pending = NeonChangeLog.objects.using('default').filter(
                    id__gt=last_log_id
                ).count()
            else:
                pending = NeonChangeLog.objects.using('default').count()

            total = NeonChangeLog.objects.using('default').count()
            self.stdout.write(f'  Pending changes on Neon:  {pending}')
            self.stdout.write(f'  Total changelog entries:  {total}')

            if pending > 0:
                self.stdout.write(self.style.WARNING(
                    f'\n  ⚠ {pending} change(s) need to be synced. '
                    f'Run without --status to apply.'
                ))
            else:
                self.stdout.write(self.style.SUCCESS(
                    '\n  ✓ Local cache is up to date.'
                ))
        except Exception as exc:
            self.stdout.write(self.style.ERROR(
                f'  Could not query Neon: {exc}'
            ))

        self.stdout.write('═' * 50)
