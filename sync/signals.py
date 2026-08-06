"""
sync/signals.py — Post-save/delete hooks for real-time sync with offline fallback.

Architecture (Neon = primary, SQLite = fast cache):
  Normal flow (Neon reachable):
    1. Write lands on 'default' (Neon) via the router.
    2. On commit: mirror to local_cache, broadcast via WS,
       AND append to NeonChangeLog (so other devices can catch up).

  Fallback flow (Neon unreachable):
    1. Router detects Neon failure -> write goes to local_cache instead.
    2. The operation is logged to SyncOutbox (pending replay).
    3. Broadcast still fires so the web dashboard refreshes.
    4. When Neon comes back, drain_sync_outbox replays pending writes
       AND the replayed changes are logged to NeonChangeLog.

  New server session catch-up:
    On startup, the server reads its last-synced NeonChangeLog ID from
    local_cache and fetches only newer entries from Neon.  This handles
    changes made by other devices while this server was offline.
    (Users already online get changes via WebSocket in real-time.)

  Bulk operations:
    Django signals don't fire for bulk_create/bulk_update/QuerySet.update()/
    QuerySet.delete().  Code that uses these MUST call the explicit helpers:
      - bulk_sync_upsert(model, pks)
      - bulk_sync_delete(model, pks)
    These log to NeonChangeLog and mirror to local_cache.

The _MIRROR_ACTIVE thread-local prevents re-entrancy.
The _SYNC_IN_PROGRESS flag prevents local_cache writes during startup sync.
"""

import logging
import os
import threading
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from django.conf import settings
from django.db import transaction as db_transaction
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.utils import timezone

logger = logging.getLogger(__name__)

_MIRROR_ACTIVE = threading.local()
_FALLBACK_ACTIVE = threading.local()
_CHANGELOG_ACTIVE = threading.local()

# Flag: set True while startup sync is replaying changelog entries.
# Prevents the signal handlers from re-mirroring rows that the sync
# thread is already writing to local_cache (avoids race conditions).
_SYNC_IN_PROGRESS = threading.Event()

SYNCED_APP_LABELS = {
    'core', 'accounts', 'catalog', 'partners', 'warehouses',
    'inventory', 'procurement', 'sales', 'audit', 'pricing',
    'pos', 'services', 'cashflow',
}


def _is_neon_primary() -> bool:
    return getattr(settings, 'SYNC_MODE', 'offline') == 'neon_primary'


def is_fallback_active() -> bool:
    return getattr(_FALLBACK_ACTIVE, 'value', False)


def set_fallback_active(active: bool) -> None:
    _FALLBACK_ACTIVE.value = active


def is_sync_in_progress() -> bool:
    """Check if the startup changelog sync is currently running."""
    return _SYNC_IN_PROGRESS.is_set()


def set_sync_in_progress(active: bool) -> None:
    """Set/clear the sync-in-progress flag (called by startup_sync)."""
    if active:
        _SYNC_IN_PROGRESS.set()
    else:
        _SYNC_IN_PROGRESS.clear()


# ── JSON-safe serialisation ────────────────────────────────────────────

def _make_json_safe(value):
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, bytes):
        return value.decode('utf-8', errors='replace')
    return str(value)


def _instance_to_dict(instance) -> dict:
    data = {}
    for field in instance._meta.concrete_fields:
        col = field.column
        raw = field.value_from_object(instance)
        data[col] = _make_json_safe(raw)
    return data


# ── Pusher (legacy) ───────────────────────────────────────────────────

_pusher_client = None


def _get_pusher():
    global _pusher_client
    if _pusher_client is not None:
        return _pusher_client
    try:
        import pusher
        app_id = getattr(settings, 'PUSHER_APP_ID', '')
        key = getattr(settings, 'PUSHER_KEY', '')
        secret = getattr(settings, 'PUSHER_SECRET', '')
        cluster = getattr(settings, 'PUSHER_CLUSTER', 'ap1')
        if not (app_id and key and secret):
            return None
        _pusher_client = pusher.Pusher(
            app_id=app_id, key=key, secret=secret, cluster=cluster, ssl=True,
        )
    except Exception as exc:
        logger.debug('Pusher init skipped: %s', exc)
    return _pusher_client


def _broadcast_pusher(tables: list[str]) -> None:
    client = _get_pusher()
    if client is None:
        return
    try:
        client.trigger('sync', 'table-changed', {'tables': tables})
    except Exception:
        pass


# ── Django Channels WebSocket broadcast ────────────────────────────────

def _broadcast_ws(tables: list[str]) -> None:
    try:
        from channels.layers import get_channel_layer
        from asgiref.sync import async_to_sync
        channel_layer = get_channel_layer()
        if channel_layer is None:
            return
        async_to_sync(channel_layer.group_send)(
            'sync',
            {'type': 'table_changed', 'tables': tables},
        )
    except Exception:
        pass


def _broadcast_ws_data(table: str, action: str, rows: list[dict]) -> None:
    try:
        from channels.layers import get_channel_layer
        from asgiref.sync import async_to_sync
        channel_layer = get_channel_layer()
        if channel_layer is None:
            return
        async_to_sync(channel_layer.group_send)(
            'sync',
            {
                'type': 'data_changed',
                'table': table,
                'action': action,
                'rows': rows,
                'timestamp': timezone.now().isoformat(),
            },
        )
    except Exception:
        pass


def broadcast_table_changed(tables: list[str]) -> None:
    _broadcast_ws(tables)
    _broadcast_pusher(tables)


def broadcast_data_changed(table: str, action: str, rows: list[dict]) -> None:
    _broadcast_ws_data(table, action, rows)
    _broadcast_pusher([table])


# ── Outbox: queue for later replay to Neon ─────────────────────────────

def _queue_to_outbox(action: str, table: str, app_label: str,
                     model_name: str, pk: int, row_data: dict | None) -> None:
    try:
        from sync.models import SyncOutbox
        SyncOutbox.objects.using('local_cache').create(
            action=action,
            db_table=table,
            app_label=app_label,
            model_name=model_name,
            row_pk=pk,
            row_data=row_data,
        )
        logger.info('Outbox queued: %s %s#%d (Neon offline)', action, table, pk)
    except Exception as exc:
        logger.error('Failed to queue outbox entry (%s %s#%d): %s', action, table, pk, exc)


# ── Neon Change Log (for cross-device catch-up) ───────────────────────

def _get_device_id() -> str:
    """Return a stable identifier for this server/device.

    Uses the DEVICE_ID env var if set, otherwise falls back to a hash of
    the machine's hostname + BASE_DIR.  This lets the startup sync skip
    changes that originated from this same device.
    """
    import hashlib
    import socket
    device_id = os.environ.get('DEVICE_ID', '')
    if device_id:
        return device_id
    raw = f'{socket.gethostname()}:{settings.BASE_DIR}'
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _log_to_neon_changelog(action: str, table: str, app_label: str,
                           model_name: str, pk: int, row_data: dict | None) -> None:
    """Append an entry to NeonChangeLog on Neon (default DB).

    This is called on_commit after a successful write to Neon.
    The changelog is the source of truth for cross-device sync —
    new server sessions read from here to catch up on missed changes.

    Guarded by _CHANGELOG_ACTIVE to prevent re-entrancy (the NeonChangeLog
    model itself is in the 'sync' app and should not trigger another log entry).
    """
    if getattr(_CHANGELOG_ACTIVE, 'value', False):
        return

    _CHANGELOG_ACTIVE.value = True
    try:
        from sync.models import NeonChangeLog
        NeonChangeLog.objects.using('default').create(
            action=action,
            db_table=table,
            app_label=app_label,
            model_name=model_name,
            row_pk=pk,
            row_data=row_data,
            source_device=_get_device_id(),
        )
    except Exception as exc:
        # Non-fatal — the change already landed on Neon, this is just
        # the log for other devices.  Log and move on.
        logger.debug('NeonChangeLog write failed (%s %s#%d): %s', action, table, pk, exc)
    finally:
        _CHANGELOG_ACTIVE.value = False




# ── On-commit orchestrator ─────────────────────────────────────────────

def _on_commit_save(sender, pk, table, app_label, model_name, row_data):
    """Enqueue background push to Neon after local_cache write commits.

    The write already landed on local_cache (instant for the user).
    This just queues the async push to Neon + changelog + WS broadcast.
    """
    from sync.background_sync import enqueue_save
    enqueue_save(sender, pk, table, app_label, model_name, row_data)


def _on_commit_delete(sender, pk, table, app_label, model_name):
    """Enqueue background push of delete to Neon."""
    from sync.background_sync import enqueue_delete
    enqueue_delete(sender, pk, table, app_label, model_name)


# ── Signal receivers ───────────────────────────────────────────────────

@receiver(post_save)
def on_model_save(sender, instance, using, **kwargs):
    if sender._meta.app_label not in SYNCED_APP_LABELS:
        return
    if getattr(_MIRROR_ACTIVE, 'value', False):
        return
    # Skip if the startup sync is writing to local_cache (avoid re-entrancy)
    if _SYNC_IN_PROGRESS.is_set():
        return

    # LOCAL-FIRST: writes go to local_cache, then background pushes to Neon
    if using == 'local_cache' and _is_neon_primary():
        pk, table = instance.pk, sender._meta.db_table
        app_label, model_name = sender._meta.app_label, sender._meta.model_name
        row_data = _instance_to_dict(instance)
        db_transaction.on_commit(
            lambda: _on_commit_save(sender, pk, table, app_label, model_name, row_data),
            using='local_cache',
        )
        return

    # Offline mode (SYNC_MODE='offline'): just broadcast
    if using == 'default' and not _is_neon_primary():
        pk, table = instance.pk, sender._meta.db_table
        row_data = _instance_to_dict(instance)
        db_transaction.on_commit(
            lambda: broadcast_data_changed(table, 'upsert', [row_data]),
            using='default',
        )


@receiver(post_delete)
def on_model_delete(sender, instance, using, **kwargs):
    if sender._meta.app_label not in SYNCED_APP_LABELS:
        return
    if getattr(_MIRROR_ACTIVE, 'value', False):
        return
    if _SYNC_IN_PROGRESS.is_set():
        return

    # LOCAL-FIRST: delete happened on local_cache, push to Neon in background
    if using == 'local_cache' and _is_neon_primary():
        pk, table = instance.pk, sender._meta.db_table
        app_label, model_name = sender._meta.app_label, sender._meta.model_name
        db_transaction.on_commit(
            lambda: _on_commit_delete(sender, pk, table, app_label, model_name),
            using='local_cache',
        )
        return

    # Offline mode
    if using == 'default' and not _is_neon_primary():
        pk, table = instance.pk, sender._meta.db_table
        db_transaction.on_commit(
            lambda: broadcast_data_changed(table, 'delete', [{'id': pk}]),
            using='default',
        )


# ═══════════════════════════════════════════════════════════════════════════════
# BULK OPERATION HELPERS
# ═══════════════════════════════════════════════════════════════════════════════
#
# Django signals (post_save, post_delete) do NOT fire for:
#   - QuerySet.update()
#   - QuerySet.delete() (bulk)
#   - bulk_create() / bulk_update()
#   - Raw SQL
#
# Any code that uses these operations on synced models MUST call the
# appropriate helper below to ensure the change actually reaches Neon and
# other devices — otherwise it silently stays local-only forever.
#
# Usage:
#   from sync.signals import bulk_sync_upsert, bulk_sync_delete
#
#   # After a QuerySet.update() or bulk_update():
#   MyModel.objects.filter(...).update(field=value)
#   bulk_sync_upsert(MyModel, list(qs.values_list('id', flat=True)))
#
#   # After a QuerySet.delete():
#   pks = list(MyModel.objects.filter(...).values_list('id', flat=True))
#   MyModel.objects.filter(pk__in=pks).delete()
#   bulk_sync_delete(MyModel, pks)
#
# IMPORTANT — these enqueue onto the background worker, they do not push to
# Neon synchronously. An earlier version of this file fetched the rows via
# `.using('default')` and wrote NeonChangeLog inline on the caller's thread,
# on the assumption that the bulk operation had written straight to Neon.
# That assumption doesn't hold in this app: AppEnvironmentRouter sends every
# unqualified write (including bulk_create/bulk_update/.update()) to
# 'local_cache' in neon_primary mode, so that fetch-from-Neon always came up
# empty and both helpers were a silent no-op. It also had no durable
# fallback — if Neon was unreachable at the exact moment a bulk operation
# ran, that sync was lost forever, unlike every other write path in this
# module, which records a SyncOutbox row before attempting anything over the
# network. Routing through enqueue_save()/enqueue_delete() (the same
# functions the per-row signal handlers use) fixes both: rows are read back
# from local_cache — where they actually are — and each one gets the same
# outbox-first durability and retry as a normal save.
# ═══════════════════════════════════════════════════════════════════════════════


def bulk_sync_upsert(model, pks: list, source: str = '') -> int:
    """
    Enqueue a batch of bulk-created/bulk-updated rows onto the background
    sync worker's queue — the same path individual saves use.

    Call this AFTER a bulk_create()/bulk_update()/QuerySet.update() on a
    synced model. Reads the rows back from local_cache (where an unqualified
    bulk write actually lands under the local-first router) and hands each
    one to enqueue_save(), which durably records it to SyncOutbox before
    queuing — so nothing is lost even if Neon is unreachable right now; the
    worker (or drain_sync_outbox on next boot) picks it up when it can.

    Args:
        model: The Django model class.
        pks: List of primary keys that were created/updated.
        source: Unused today (kept for call-site compatibility) — the queue
            path always attributes changes to this device's own id.

    Returns:
        Number of rows enqueued.
    """
    if not pks:
        return 0
    if model._meta.app_label not in SYNCED_APP_LABELS:
        return 0
    if not _is_neon_primary():
        return 0

    from sync.background_sync import enqueue_save

    table = model._meta.db_table
    app_label = model._meta.app_label
    model_name = model._meta.model_name

    BATCH_SIZE = 500
    queued = 0

    for i in range(0, len(pks), BATCH_SIZE):
        batch_pks = pks[i:i + BATCH_SIZE]

        # Read back the current state from local_cache — that's where the
        # router actually put these rows, not Neon.
        objs = model._default_manager.using('local_cache').filter(pk__in=batch_pks)

        for obj in objs:
            row_data = _instance_to_dict(obj)
            enqueue_save(model, obj.pk, table, app_label, model_name, row_data)
            queued += 1

    return queued


def bulk_sync_delete(model, pks: list, source: str = '') -> int:
    """
    Enqueue a batch of bulk-deleted rows onto the background sync worker's
    queue — the same path individual deletes use.

    Call this AFTER a QuerySet.delete() on a synced model — the rows must
    already be gone from local_cache by the time this runs (a bare
    QuerySet.delete() already routes there under the local-first router).
    Each pk gets the same outbox-first durability as a normal delete.

    Args:
        model: The Django model class.
        pks: List of primary keys that were deleted.
        source: Unused today (kept for call-site compatibility).

    Returns:
        Number of rows enqueued.
    """
    if not pks:
        return 0
    if model._meta.app_label not in SYNCED_APP_LABELS:
        return 0
    if not _is_neon_primary():
        return 0

    from sync.background_sync import enqueue_delete

    table = model._meta.db_table
    app_label = model._meta.app_label
    model_name = model._meta.model_name

    for pk in pks:
        enqueue_delete(model, pk, table, app_label, model_name)

    return len(pks)
