"""
sync/signals.py — Post-save/delete hooks for real-time sync with offline fallback.

Architecture (Neon = primary, SQLite = fast cache):
  Normal flow (Neon reachable):
    1. Write lands on 'default' (Neon) via the router.
    2. On commit: mirror to local_cache, broadcast via WS.

  Fallback flow (Neon unreachable):
    1. Router detects Neon failure -> write goes to local_cache instead.
    2. The operation is logged to SyncOutbox (pending replay).
    3. Broadcast still fires so the web dashboard refreshes.
    4. When Neon comes back, drain_sync_outbox replays pending writes.

The _MIRROR_ACTIVE thread-local prevents re-entrancy.
"""

import logging
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


# ── Local cache mirror (Neon -> SQLite) ────────────────────────────────

def _mirror_to_local_cache(sender, pk: int) -> None:
    if not _is_neon_primary():
        return
    if getattr(_MIRROR_ACTIVE, 'value', False):
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
    except Exception as exc:
        logger.warning('Local cache mirror failed (%s pk=%s): %s', sender.__name__, pk, exc)
    finally:
        _MIRROR_ACTIVE.value = False


def _mirror_delete_to_local_cache(sender, pk: int) -> None:
    if not _is_neon_primary():
        return
    if getattr(_MIRROR_ACTIVE, 'value', False):
        return

    _MIRROR_ACTIVE.value = True
    try:
        sender._default_manager.using('local_cache').filter(pk=pk).delete()
    except Exception as exc:
        logger.warning('Local cache mirror-delete failed (%s pk=%s): %s', sender.__name__, pk, exc)
    finally:
        _MIRROR_ACTIVE.value = False


# ── On-commit orchestrator ─────────────────────────────────────────────

def _on_commit_save(sender, pk, table, row_data):
    if not is_fallback_active():
        _mirror_to_local_cache(sender, pk)
    broadcast_data_changed(table, 'upsert', [row_data])


def _on_commit_delete(sender, pk, table):
    if not is_fallback_active():
        _mirror_delete_to_local_cache(sender, pk)
    broadcast_data_changed(table, 'delete', [{'id': pk}])


# ── Signal receivers ───────────────────────────────────────────────────

@receiver(post_save)
def on_model_save(sender, instance, using, **kwargs):
    if sender._meta.app_label not in SYNCED_APP_LABELS:
        return
    if getattr(_MIRROR_ACTIVE, 'value', False):
        return

    # Normal Neon path
    if using == 'default' and _is_neon_primary():
        pk, table = instance.pk, sender._meta.db_table
        row_data = _instance_to_dict(instance)
        db_transaction.on_commit(
            lambda: _on_commit_save(sender, pk, table, row_data),
            using='default',
        )
        return

    # Fallback path: written to local_cache because Neon was down
    if using == 'local_cache' and is_fallback_active():
        pk, table = instance.pk, sender._meta.db_table
        row_data = _instance_to_dict(instance)
        _queue_to_outbox(
            action='upsert',
            table=table,
            app_label=sender._meta.app_label,
            model_name=sender._meta.model_name,
            pk=pk,
            row_data=row_data,
        )
        db_transaction.on_commit(
            lambda: broadcast_data_changed(table, 'upsert', [row_data]),
            using='local_cache',
        )
        return

    # Offline mode (SYNC_MODE='offline'): default IS local_cache
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

    # Normal Neon path
    if using == 'default' and _is_neon_primary():
        pk, table = instance.pk, sender._meta.db_table
        db_transaction.on_commit(
            lambda: _on_commit_delete(sender, pk, table),
            using='default',
        )
        return

    # Fallback path
    if using == 'local_cache' and is_fallback_active():
        pk, table = instance.pk, sender._meta.db_table
        _queue_to_outbox(
            action='delete',
            table=table,
            app_label=sender._meta.app_label,
            model_name=sender._meta.model_name,
            pk=pk,
            row_data=None,
        )
        db_transaction.on_commit(
            lambda: broadcast_data_changed(table, 'delete', [{'id': pk}]),
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
