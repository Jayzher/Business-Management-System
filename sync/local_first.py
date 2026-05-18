"""
sync/local_first.py — Local-first write pattern for instant UI response.

For operations where the user shouldn't wait for Neon (especially deletes),
this module provides helpers that:
  1. Apply the change to local_cache IMMEDIATELY (user sees it done)
  2. Queue the same change to Neon via the background worker
  3. Return instantly — no Neon round-trip blocking the response

This is safe because:
  - Neon is the source of truth, but local_cache is what the user sees
  - The background worker will apply the change to Neon within milliseconds
  - If the Neon write fails, it's queued to the SyncOutbox for retry
  - The NeonChangeLog ensures other devices catch up on next boot

Usage:
    from sync.local_first import local_first_soft_delete, local_first_hard_delete

    # In a view:
    local_first_soft_delete(supplier)   # instant soft-delete
    local_first_hard_delete(invoice)    # instant hard-delete
"""

import logging
import threading

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

# Guard against re-entrancy from signals
_LOCAL_FIRST_ACTIVE = threading.local()


def local_first_soft_delete(instance):
    """
    Soft-delete: set is_active=False on local_cache immediately,
    then queue the same update to Neon in the background.

    The user sees the record disappear instantly.
    """
    sender = type(instance)
    pk = instance.pk
    table = sender._meta.db_table
    app_label = sender._meta.app_label
    model_name = sender._meta.model_name

    # 1. Apply to local_cache immediately (what the user reads from)
    try:
        sender.all_objects.using('local_cache').filter(pk=pk).update(
            is_active=False, updated_at=timezone.now()
        )
    except Exception as exc:
        logger.warning('Local-first soft_delete failed on local_cache (%s pk=%s): %s',
                       sender.__name__, pk, exc)

    # 2. Update the in-memory instance
    instance.is_active = False

    # 3. Queue the Neon write in the background
    _enqueue_neon_soft_delete(sender, pk, table, app_label, model_name)

    # 4. Broadcast immediately so other connected clients see the change
    from sync.signals import broadcast_data_changed, _instance_to_dict
    row_data = _instance_to_dict(instance)
    broadcast_data_changed(table, 'upsert', [row_data])


def local_first_hard_delete(instance):
    """
    Hard-delete: remove from local_cache immediately,
    then queue the delete to Neon in the background.

    The user sees the record disappear instantly.
    """
    sender = type(instance)
    pk = instance.pk
    table = sender._meta.db_table
    app_label = sender._meta.app_label
    model_name = sender._meta.model_name

    # 1. Delete from local_cache immediately
    try:
        sender._default_manager.using('local_cache').filter(pk=pk).delete()
    except Exception as exc:
        logger.warning('Local-first hard_delete failed on local_cache (%s pk=%s): %s',
                       sender.__name__, pk, exc)

    # 2. Queue the Neon delete in the background
    _enqueue_neon_hard_delete(sender, pk, table, app_label, model_name)

    # 3. Broadcast immediately
    from sync.signals import broadcast_data_changed
    broadcast_data_changed(table, 'delete', [{'id': pk}])


def _enqueue_neon_soft_delete(sender, pk, table, app_label, model_name):
    """Queue a soft-delete (UPDATE is_active=False) to Neon via background worker."""
    from sync.background_sync import _task_queue
    import time

    _task_queue.put({
        'type': 'neon_soft_delete',
        'sender': sender,
        'pk': pk,
        'table': table,
        'app_label': app_label,
        'model_name': model_name,
        'enqueued_at': time.time(),
    })


def _enqueue_neon_hard_delete(sender, pk, table, app_label, model_name):
    """Queue a hard-delete (DELETE) to Neon via background worker."""
    from sync.background_sync import _task_queue
    import time

    _task_queue.put({
        'type': 'neon_hard_delete',
        'sender': sender,
        'pk': pk,
        'table': table,
        'app_label': app_label,
        'model_name': model_name,
        'enqueued_at': time.time(),
    })
