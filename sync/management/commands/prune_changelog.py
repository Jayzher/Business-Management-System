"""
Prune old NeonChangeLog entries from Neon.

Usage:
    python manage.py prune_changelog
    python manage.py prune_changelog --days 14
    python manage.py prune_changelog --dry-run

Retention policy:
  By default, entries older than 7 days are deleted.  Any server that
  hasn't synced in 7 days should do a full hydration anyway (the startup
  sync handles this gracefully by falling back to full hydration when the
  checkpoint is missing or the referenced log_id no longer exists).
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta


class Command(BaseCommand):
    help = 'Delete old NeonChangeLog entries from Neon (default DB).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=7,
            help='Delete entries older than this many days (default: 7).',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be deleted without actually deleting.',
        )

    def handle(self, *args, **options):
        days = options['days']
        dry_run = options['dry_run']

        from sync.models import NeonChangeLog

        cutoff = timezone.now() - timedelta(days=days)
        old_entries = NeonChangeLog.objects.using('default').filter(
            created_at__lt=cutoff
        )
        count = old_entries.count()

        if count == 0:
            self.stdout.write('No changelog entries older than %d days.' % days)
            return

        if dry_run:
            self.stdout.write(
                f'Would delete {count} changelog entries older than {days} days '
                f'(before {cutoff.isoformat()}).'
            )
            return

        deleted, _ = old_entries.delete()
        self.stdout.write(self.style.SUCCESS(
            f'Deleted {deleted} changelog entries older than {days} days.'
        ))
