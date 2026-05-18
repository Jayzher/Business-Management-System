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


# ── Local cache mirror (Neon -> SQLite) ────────────────────────────────

def _mirror_to_local_cache(sender, pk: int) -> None:
    if not _is_neon_primary():
        return
    if getattr(_MIRROR_ACTIVE, 'value', False):
        return
    # Skip if startup sync is running — it handles local_cache writes.
    # This prevents race conditions where both the signal and the sync
    # thread try to write the same row to local_cache simultaneously.
    if _SYNC_IN_PROGRESS.is_set():
        return

    _MIRROR_ACTIVE.value = True
    try:
        obj = sender._default_manager.using('default').filter(pk=pk).first()
        if obj is None:
            return

        concrete_fields = [
            f for f in sender._meta.concrete_fields if not f.primary_key
        ]
        update_fields = [f.attname for f in concrete_fields]

        # Temporarily disable auto_now so timestamps are preserved from Neon
        auto_fields = []
        for field in sender._meta.get_fields():
            if hasattr(field, 'auto_now') and field.auto_now:
                field.auto_now = False
                auto_fields.append(('auto_now', field))
            if hasattr(field, 'auto_now_add') and field.auto_now_add:
                field.auto_now_add = False
                auto_fields.append(('auto_now_add', field))

        try:
            obj._state.adding = True
            obj._state.db = 'local_cache'

            if update_fields:
                sender._default_manager.using('local_cache').bulk_create(
                    [obj],
                    update_conflicts=True,
                    update_fields=update_fields,
                    unique_fields=['id'],
                )
            else:
                sender._default_manager.using('local_cache').bulk_create(
                    [obj], ignore_conflicts=True,
                )
        finally:
            for attr, field in auto_fields:
                setattr(field, attr, True)
    except Exception as exc:
        logger.warning('Local cache mirror failed (%s pk=%s): %s', sender.__name__, pk, exc)
    finally:
        _MIRROR_ACTIVE.value = False


def _mirror_delete_to_local_cache(sender, pk: int) -> None:
    if not _is_neon_primary():
        return
    if getattr(_MIRROR_ACTIVE, 'value', False):
        return
    if _SYNC_IN_PROGRESS.is_set():
        return

    _MIRROR_ACTIVE.value = True
    try:
        sender._default_manager.using('local_cache').filter(pk=pk).delete()
    except Exception as exc:
        logger.warning('Local cache mirror-delete failed (%s pk=%s): %s', sender.__name__, pk, exc)
    finally:
        _MIRROR_ACTIVE.value = False


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
# appropriate helper below to ensure:
#   1. The change is logged to NeonChangeLog (for other devices)
#   2. The change is mirrored to local_cache (for this device)
#   3. A WebSocket broadcast is sent (for connected clients)
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
# ═══════════════════════════════════════════════════════════════════════════════


def bulk_sync_upsert(model, pks: list, source: str = '') -> int:
    """
    Log + mirror a batch of upserted rows to NeonChangeLog and local_cache.

    Call this AFTER a bulk_create/bulk_update/QuerySet.update() on Neon.
    The rows must already exist on Neon (default DB) at the time of this call.

    Args:
        model: The Django model class.
        pks: List of primary keys that were created/updated.
        source: Optional label for source_device in the changelog.

    Returns:
        Number of rows successfully synced.
    """
    if not pks:
        return 0
    if model._meta.app_label not in SYNCED_APP_LABELS:
        return 0
    if not _is_neon_primary():
        return 0

    table = model._meta.db_table
    app_label = model._meta.app_label
    model_name = model._meta.model_name
    device_id = source or _get_device_id()

    BATCH_SIZE = 200
    synced = 0

    for i in range(0, len(pks), BATCH_SIZE):
        batch_pks = pks[i:i + BATCH_SIZE]

        # Fetch current state from Neon
        objs = list(
            model._default_manager.using('default').filter(pk__in=batch_pks)
        )

        # Log each to NeonChangeLog
        changelog_entries = []
        for obj in objs:
            row_data = _instance_to_dict(obj)
            changelog_entries.append({
                'action': 'upsert',
                'table': table,
                'app_label': app_label,
                'model_name': model_name,
                'pk': obj.pk,
                'row_data': row_data,
                'device_id': device_id,
            })

        # Batch-insert changelog entries
        if changelog_entries:
            _bulk_log_to_neon_changelog(changelog_entries)

        # Mirror to local_cache (upsert)
        if objs and not _SYNC_IN_PROGRESS.is_set():
            _bulk_mirror_to_local_cache(model, objs)

        synced += len(objs)

    # Broadcast
    if synced > 0:
        broadcast_table_changed([table])

    return synced


def bulk_sync_delete(model, pks: list, source: str = '') -> int:
    """
    Log + mirror a batch of deleted rows to NeonChangeLog and local_cache.

    Call this AFTER a QuerySet.delete() on Neon.
    The rows must already be deleted from Neon at the time of this call.

    Args:
        model: The Django model class.
        pks: List of primary keys that were deleted.
        source: Optional label for source_device in the changelog.

    Returns:
        Number of rows logged.
    """
    if not pks:
        return 0
    if model._meta.app_label not in SYNCED_APP_LABELS:
        return 0
    if not _is_neon_primary():
        return 0

    table = model._meta.db_table
    app_label = model._meta.app_label
    model_name = model._meta.model_name
    device_id = source or _get_device_id()

    # Log to NeonChangeLog
    changelog_entries = []
    for pk in pks:
        changelog_entries.append({
            'action': 'delete',
            'table': table,
            'app_label': app_label,
            'model_name': model_name,
            'pk': pk,
            'row_data': None,
            'device_id': device_id,
        })

    if changelog_entries:
        _bulk_log_to_neon_changelog(changelog_entries)

    # Mirror deletes to local_cache
    if not _SYNC_IN_PROGRESS.is_set():
        try:
            model._default_manager.using('local_cache').filter(pk__in=pks).delete()
        except Exception as exc:
            logger.warning('Bulk mirror-delete failed (%s): %s', model.__name__, exc)

    # Broadcast
    broadcast_data_changed(table, 'delete', [{'id': pk} for pk in pks])

    return len(pks)


def _bulk_log_to_neon_changelog(entries: list[dict]) -> None:
    """Batch-insert multiple entries to NeonChangeLog on Neon."""
    if getattr(_CHANGELOG_ACTIVE, 'value', False):
        return

    _CHANGELOG_ACTIVE.value = True
    try:
        from sync.models import NeonChangeLog
        objs = [
            NeonChangeLog(
                action=e['action'],
                db_table=e['table'],
                app_label=e['app_label'],
                model_name=e['model_name'],
                row_pk=e['pk'],
                row_data=e['row_data'],
                source_device=e.get('device_id', ''),
            )
            for e in entries
        ]
        NeonChangeLog.objects.using('default').bulk_create(objs)
    except Exception as exc:
        logger.debug('Bulk NeonChangeLog write failed: %s', exc)
    finally:
        _CHANGELOG_ACTIVE.value = False


def _bulk_mirror_to_local_cache(model, objs: list) -> None:
    """Upsert a batch of objects to local_cache."""
    if getattr(_MIRROR_ACTIVE, 'value', False):
        return

    _MIRROR_ACTIVE.value = True
    try:
        concrete_fields = [
            f for f in model._meta.concrete_fields if not f.primary_key
        ]
        update_fields = [f.attname for f in concrete_fields]

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
            for obj in objs:
                obj._state.adding = True
                obj._state.db = 'local_cache'

            if update_fields:
                model._default_manager.using('local_cache').bulk_create(
                    objs,
                    update_conflicts=True,
                    update_fields=update_fields,
                    unique_fields=['id'],
                )
            else:
                model._default_manager.using('local_cache').bulk_create(
                    objs, ignore_conflicts=True,
                )
        finally:
            for attr, field in auto_fields:
                setattr(field, attr, True)
    except Exception as exc:
        logger.warning('Bulk mirror to local_cache failed (%s): %s', model.__name__, exc)
    finally:
        _MIRROR_ACTIVE.value = False
