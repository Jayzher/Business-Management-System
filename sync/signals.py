"""
sync/signals.py — Post-save hooks for event-driven cross-DB sync.

When any web-admin model save hits the default (SQLite) database:
  1. A background thread asynchronously writes the same row to Neon so
     mobile clients that read Neon directly can see the change.
  2. A WebSocket broadcast is sent via Django Channels to all connected
     clients (web + mobile) on the 'sync' group with TWO event types:
       a) {"type": "table_changed", "tables": [<db_table_name>]}
          — lightweight notification for clients that pull from Neon
       b) {"type": "data_changed", "table": <db_table_name>,
           "action": "upsert"|"delete", "rows": [...]}
          — carries the actual row data so clients can apply changes
            to their local DB instantly without a separate pull/query.
  3. (Legacy) A Pusher event is also triggered if credentials are configured,
     for any mobile clients still using the Pusher SDK.

The _NEON_WRITE_ACTIVE thread-local prevents re-entrancy if the async
thread itself triggers a post_save (e.g. via bulk_create).
"""

import logging
import threading
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from django.db import transaction as db_transaction
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.utils import timezone

logger = logging.getLogger(__name__)

_NEON_WRITE_ACTIVE = threading.local()

SYNCED_APP_LABELS = {
    'core', 'accounts', 'catalog', 'partners', 'warehouses',
    'inventory', 'procurement', 'sales', 'audit', 'pricing',
    'pos', 'services', 'cashflow',
}


# ── JSON-safe serialisation helper ─────────────────────────────────────
def _make_json_safe(value):
    """Convert a model field value to a JSON-serialisable Python type."""
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
    """
    Serialise a Django model instance to a dict of {db_column: value}
    using only concrete (non-relation) fields.  All values are JSON-safe.
    """
    data = {}
    for field in instance._meta.concrete_fields:
        col = field.column  # actual DB column name (e.g. 'category_id')
        raw = field.value_from_object(instance)
        data[col] = _make_json_safe(raw)
    return data


# ── Pusher (legacy, optional) ─────────────────────────────────────────
_pusher_client = None


def _get_pusher():
    """Lazy-init a shared Pusher client; returns None if credentials missing."""
    global _pusher_client
    if _pusher_client is not None:
        return _pusher_client
    try:
        from django.conf import settings
        import pusher
        app_id = getattr(settings, 'PUSHER_APP_ID', '')
        key    = getattr(settings, 'PUSHER_KEY',    '')
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
    """Legacy Pusher broadcast — fails silently when unavailable."""
    client = _get_pusher()
    if client is None:
        return
    try:
        client.trigger('sync', 'table-changed', {'tables': tables})
        logger.debug('Pusher triggered table-changed: %s', tables)
    except Exception as exc:
        logger.debug('Pusher trigger skipped (%s): %s', tables, exc)


# ── Django Channels WebSocket broadcast ────────────────────────────────
def _broadcast_ws(tables: list[str]) -> None:
    """
    Send a table_changed event to every connected WebSocket client via
    the Django Channels layer.  Works from synchronous code (signal handlers)
    by using async_to_sync.
    """
    try:
        from channels.layers import get_channel_layer
        from asgiref.sync import async_to_sync
        channel_layer = get_channel_layer()
        if channel_layer is None:
            return
        async_to_sync(channel_layer.group_send)(
            'sync',
            {
                'type': 'table_changed',
                'tables': tables,
            },
        )
        logger.debug('WS broadcast table-changed: %s', tables)
    except Exception as exc:
        logger.debug('WS broadcast skipped (%s): %s', tables, exc)


def _broadcast_ws_data(table: str, action: str, rows: list[dict]) -> None:
    """
    Send a data_changed event carrying the actual row data so clients
    can apply changes to their local DB without a separate pull.

    action: 'upsert' | 'delete'
    rows:   list of dicts — full row for upsert, just {'id': pk} for delete.
    """
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
        logger.debug('WS broadcast data-changed: %s %s (%d rows)', action, table, len(rows))
    except Exception as exc:
        logger.debug('WS data broadcast skipped (%s): %s', table, exc)


def broadcast_table_changed(tables: list[str]) -> None:
    """
    Broadcast a table-changed event to all real-time clients.
    Sends via both Django Channels (primary) and Pusher (legacy fallback).
    """
    _broadcast_ws(tables)
    _broadcast_pusher(tables)


def broadcast_data_changed(table: str, action: str, rows: list[dict]) -> None:
    """
    Broadcast a data-changed event with the actual row data.
    Also sends the lightweight table_changed for backward compatibility.
    """
    _broadcast_ws_data(table, action, rows)
    # Legacy Pusher gets the lightweight notification only
    _broadcast_pusher([table])


# ── Neon write-through ─────────────────────────────────────────────────
def _write_to_neon_async(sender, pk: int, table: str, row_data: dict) -> None:
    """
    Spawn a daemon thread that upserts the record identified by *pk* into the
    'neon' database alias.  Broadcasts the event only after the write
    succeeds so clients never receive a stale-read notification.

    row_data is the pre-serialised dict captured at signal time so the
    broadcast carries the actual data even if the background thread is slow.
    """
    if getattr(_NEON_WRITE_ACTIVE, 'value', False):
        return

    def _worker():
        _NEON_WRITE_ACTIVE.value = True
        try:
            from core.management.commands.db_sync import Command
            Command._ensure_both_databases()
            from django.db import connections
            if 'neon' not in connections.databases:
                return

            obj = sender._default_manager.using('default').filter(pk=pk).first()
            if obj is None:
                return

            concrete_fields = [
                f for f in sender._meta.concrete_fields if not f.primary_key
            ]
            update_fields = [f.attname for f in concrete_fields]
            if update_fields:
                sender._default_manager.using('neon').bulk_create(
                    [obj],
                    update_conflicts=True,
                    update_fields=update_fields,
                    unique_fields=['id'],
                )
            else:
                sender._default_manager.using('neon').bulk_create(
                    [obj], ignore_conflicts=True,
                )
            # Notify clients with the actual row data after Neon has it
            broadcast_data_changed(table, 'upsert', [row_data])
        except Exception as exc:
            logger.debug(
                'Neon write-through skipped (%s pk=%s): %s', sender.__name__, pk, exc
            )
        finally:
            _NEON_WRITE_ACTIVE.value = False

    threading.Thread(target=_worker, daemon=True, name=f'neon-wt-{sender.__name__}').start()


def _delete_from_neon_async(sender, pk: int, table: str) -> None:
    """Propagate a hard delete to Neon. Fails silently if Neon is unavailable."""
    if getattr(_NEON_WRITE_ACTIVE, 'value', False):
        return

    def _worker():
        _NEON_WRITE_ACTIVE.value = True
        try:
            from core.management.commands.db_sync import Command
            Command._ensure_both_databases()
            from django.db import connections
            if 'neon' not in connections.databases:
                return
            sender._default_manager.using('neon').filter(pk=pk).delete()
            broadcast_data_changed(table, 'delete', [{'id': pk}])
        except Exception as exc:
            logger.debug(
                'Neon delete skipped (%s pk=%s): %s', sender.__name__, pk, exc
            )
        finally:
            _NEON_WRITE_ACTIVE.value = False

    threading.Thread(target=_worker, daemon=True, name=f'neon-del-{sender.__name__}').start()


# ── Signal receivers ───────────────────────────────────────────────────
@receiver(post_save)
def on_model_save(sender, instance, using, **kwargs):
    if using != 'default':
        return
    if sender._meta.app_label not in SYNCED_APP_LABELS:
        return
    if getattr(_NEON_WRITE_ACTIVE, 'value', False):
        return

    # Capture the row data NOW while the instance is still in memory.
    # The background thread may run later when the instance is stale.
    pk, table = instance.pk, sender._meta.db_table
    row_data = _instance_to_dict(instance)

    db_transaction.on_commit(
        lambda: _write_to_neon_async(sender, pk, table, row_data)
    )


@receiver(post_delete)
def on_model_delete(sender, instance, using, **kwargs):
    if using != 'default':
        return
    if sender._meta.app_label not in SYNCED_APP_LABELS:
        return
    if getattr(_NEON_WRITE_ACTIVE, 'value', False):
        return

    pk, table = instance.pk, sender._meta.db_table
    db_transaction.on_commit(
        lambda: _delete_from_neon_async(sender, pk, table)
    )
