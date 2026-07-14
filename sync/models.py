"""
sync/models.py — Models for offline-resilient sync between Neon and local_cache.

Two key models:

1. SyncOutbox (lives on local_cache / SQLite):
   When Neon is unreachable, writes fall back to local_cache.
   Each fallback write is logged here so it can be replayed to Neon
   when connectivity is restored.

2. NeonChangeLog (lives on default / Neon):
   Every write to Neon is recorded here as a sequential change log entry.
   When a local server starts a new session, it compares its last-synced
   log_id against the Neon change log and pulls only the delta.
   This handles the case where another device wrote to Neon while this
   server was offline — users already online get changes via WebSocket,
   but new server sessions need this log to catch up.
"""

from django.db import models
from django.utils import timezone


# ═══════════════════════════════════════════════════════════════════════════════
# SyncOutbox — queued writes for replay to Neon when connectivity is restored
# ═══════════════════════════════════════════════════════════════════════════════

class SyncOutboxStatus(models.TextChoices):
    PENDING = 'PENDING', 'Pending'
    SYNCED = 'SYNCED', 'Synced'
    FAILED = 'FAILED', 'Failed'


class SyncOutbox(models.Model):
    """
    Each row represents a write that landed on local_cache because Neon
    was unreachable.  The drain process replays these to Neon in order.
    """
    # What happened
    action = models.CharField(
        max_length=10,
        choices=[('upsert', 'Upsert'), ('delete', 'Delete')],
    )
    # Which table and row
    db_table = models.CharField(max_length=100, db_index=True)
    app_label = models.CharField(max_length=50)
    model_name = models.CharField(max_length=50)
    row_pk = models.IntegerField()

    # Serialised row data (JSON) — only for upserts.
    # For deletes, we just need the PK.
    row_data = models.JSONField(null=True, blank=True)

    # Lifecycle
    status = models.CharField(
        max_length=10,
        choices=SyncOutboxStatus.choices,
        default=SyncOutboxStatus.PENDING,
        db_index=True,
    )
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    synced_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True, default='')
    retry_count = models.IntegerField(default=0)

    class Meta:
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['status', 'created_at']),
        ]

    def __str__(self):
        return f"Outbox#{self.pk} {self.action} {self.db_table}#{self.row_pk} [{self.status}]"


# ═══════════════════════════════════════════════════════════════════════════════
# NeonChangeLog — sequential change log stored on Neon (PostgreSQL)
# ═══════════════════════════════════════════════════════════════════════════════

class NeonChangeLog(models.Model):
    """
    Sequential log of every write that lands on Neon.

    Purpose:
      When a local server starts a new session, it reads its last-synced
      log_id from local_cache (SyncCheckpoint) and fetches all NeonChangeLog
      entries with id > last_synced_id.  It then replays those changes to
      local_cache, bringing it up to date without a full table scan.

    This solves the "another device wrote to Neon while I was offline" problem.
    Users already connected via WebSocket receive changes in real-time, but
    new server sessions (cold starts, restarts) use this log to catch up.

    Retention:
      Old entries can be pruned periodically (e.g. older than 7 days) since
      any server that hasn't synced in 7 days should do a full hydration anyway.
    """
    # Sequential ID is the primary key (auto-increment on Postgres)
    # — this is the "cursor" that local servers track.

    # What changed
    action = models.CharField(
        max_length=10,
        choices=[('upsert', 'Upsert'), ('delete', 'Delete')],
    )
    db_table = models.CharField(max_length=100, db_index=True)
    app_label = models.CharField(max_length=50)
    model_name = models.CharField(max_length=50)
    row_pk = models.BigIntegerField()

    # Serialised row data (JSON) — for upserts, contains the full row.
    # For deletes, null (we only need the PK to remove locally).
    row_data = models.JSONField(null=True, blank=True)

    # When the change was recorded
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    # Who/what caused the change (optional context)
    source_device = models.CharField(
        max_length=100, blank=True, default='',
        help_text='Identifier of the device/server that made the change.',
    )

    class Meta:
        ordering = ['id']
        indexes = [
            models.Index(fields=['db_table', 'created_at']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f"ChangeLog#{self.pk} {self.action} {self.db_table}#{self.row_pk}"


# ═══════════════════════════════════════════════════════════════════════════════
# ChangelogReplayFailure — Neon→local_cache changelog entries that failed
# ═══════════════════════════════════════════════════════════════════════════════

class ChangelogReplayFailure(models.Model):
    """
    A NeonChangeLog entry that raised while being replayed to local_cache
    (sync/startup_sync.py::_replay_changelog_entries).

    Previously a failure here was just skipped — logged at debug level and
    the sync checkpoint moved past it, permanently. That silently produced
    orphaned/stale rows in local_cache with no record that anything had
    gone wrong. This table makes failures visible and retryable: each
    failing row is recorded here (keyed by db_table+row_pk, so repeated
    failures for the same row update one record instead of piling up),
    and `manage.py retry_changelog_failures` re-attempts them against the
    current state on Neon.
    """
    changelog_id = models.BigIntegerField(
        db_index=True,
        help_text='The NeonChangeLog id that last failed for this row.',
    )
    action = models.CharField(
        max_length=10,
        choices=[('upsert', 'Upsert'), ('delete', 'Delete')],
    )
    db_table = models.CharField(max_length=100, db_index=True)
    app_label = models.CharField(max_length=50)
    model_name = models.CharField(max_length=50)
    row_pk = models.BigIntegerField()

    error_message = models.TextField(blank=True, default='')
    attempts = models.IntegerField(default=1)
    first_failed_at = models.DateTimeField(default=timezone.now)
    last_failed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-last_failed_at']
        constraints = [
            models.UniqueConstraint(fields=['db_table', 'row_pk'], name='sync_changelogfail_table_pk_uniq'),
        ]

    def __str__(self):
        return f"ReplayFailure {self.db_table}#{self.row_pk} (attempts={self.attempts})"
