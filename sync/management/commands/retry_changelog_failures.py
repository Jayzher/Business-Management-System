"""
Retry NeonChangeLog entries that previously failed to replay to local_cache.

sync/startup_sync.py::_replay_changelog_entries records a ChangelogReplayFailure
row (instead of silently skipping) whenever applying an entry raises — a
transient lock, a brief FK-ordering conflict during a burst of related writes,
anything. The normal replay loop moves its checkpoint past these regardless
(so one stuck row can't stall everything after it), which means they're
never retried automatically. This command is that retry.

Usage:
    python manage.py retry_changelog_failures
    python manage.py retry_changelog_failures --dry-run
"""

from django.apps import apps
from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = 'Retry changelog entries that failed to replay to local_cache.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be retried without applying anything.',
        )

    def handle(self, *args, **options):
        from django.conf import settings
        from sync.models import ChangelogReplayFailure
        from sync.startup_sync import _apply_changelog_entry

        sync_mode = getattr(settings, 'SYNC_MODE', 'offline')
        if sync_mode == 'offline':
            self.stdout.write(self.style.WARNING(
                'SYNC_MODE is "offline" — nothing to retry.'
            ))
            return

        failures = list(ChangelogReplayFailure.objects.using('local_cache').all())
        if not failures:
            self.stdout.write(self.style.SUCCESS('No recorded replay failures.'))
            return

        self.stdout.write(f'Retrying {len(failures)} failed entr{"y" if len(failures) == 1 else "ies"}...')

        from sync.background_sync import pause_worker, resume_worker
        pause_worker()
        try:
            resolved, still_failing = 0, 0
            for failure in failures:
                if options['dry_run']:
                    self.stdout.write(
                        f'  would retry {failure.db_table}#{failure.row_pk} '
                        f'(attempts so far: {failure.attempts})'
                    )
                    continue
                try:
                    # ChangelogReplayFailure exposes the same attributes
                    # (.action/.app_label/.model_name/.row_pk) that
                    # _apply_changelog_entry expects from a NeonChangeLog entry.
                    _apply_changelog_entry(failure, apps)
                    failure.delete()
                    resolved += 1
                    self.stdout.write(self.style.SUCCESS(
                        f'  resolved {failure.db_table}#{failure.row_pk}'
                    ))
                except Exception as exc:
                    still_failing += 1
                    failure.error_message = str(exc)[:2000]
                    failure.last_failed_at = timezone.now()
                    failure.attempts += 1
                    failure.save(update_fields=['error_message', 'last_failed_at', 'attempts'])
                    self.stdout.write(self.style.ERROR(
                        f'  still failing {failure.db_table}#{failure.row_pk}: {exc}'
                    ))
        finally:
            resume_worker()

        if options['dry_run']:
            return

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(f'Resolved: {resolved}'))
        if still_failing:
            self.stdout.write(self.style.WARNING(
                f'Still failing: {still_failing} — these likely need '
                f'`reconcile_local_cache` or manual investigation.'
            ))
