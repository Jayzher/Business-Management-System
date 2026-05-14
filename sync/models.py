"""
sync/models.py — Outbox model for offline-resilient sync.

When Neon is unreachable, writes fall back to local_cache (SQLite).
Each fallback write is logged here so it can be replayed to Neon
when connectivity is restored.

The outbox is drained by:
  - The `drain_sync_outbox` management command (cron / manual)
  - The Tests & Syncs page "Drain Outbox" action
  - Automatically on the next successful Neon write (piggyback drain)
"""

from django.db import models
from django.utils import timezone


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
