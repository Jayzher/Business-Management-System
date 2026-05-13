"""
sync/signals.py — Post-save/delete hooks for real-time sync.

Architecture (Phase 2 — Neon = primary):
  - All writes go to 'default' (Neon PostgreSQL).
  - On commit, the signal:
      1. Mirrors the row to 'local_cache' (SQLite) synchronously (~1ms).
      2. Broadcasts via Django Channels WebSocket to all connected clients.
      3. (Legacy) Triggers Pusher for older mobile clients.

  - Mobile clients receive the actual row data via WS and apply it to
    their local Drift DB without a Neon round-trip.
  - Web clients receive the event and refresh the page content area.

In offline mode (SYNC_MODE = 'offline'):
  - default IS local_cache (same SQLite file), so the mirror is a no-op.
  - Broadcasts still fire so the web dashboard refreshes.

The _MIRROR_ACTIVE thread-local prevents re-entrancy when the mirror
write itself triggers a post_save.
"""

import logging
import threading
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from django.conf import settings
from django.db import connections, transaction as db_transaction
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.utils import timezone

logger = logging.getLogger(__name__)

_MIRROR_ACTIVE = threading.local()

SYNCED_APP_LABELS = {
    'core', 'accounts', 'catalog', 'partners', 'warehouses',
    'inventory', 'procurement', 'sales', 'audit', 'pricing',
    'pos', 'services', 'cashflow',
}


def _is_neon_primary() -> bool:
    """True when Neon is the authoritative write target."""
    return getattr(settings, 'SYNC_MODE', 'offline') == 'neon_primary'


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
    the Django Channels layer.
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


# ── Local cache mirror (Neon → SQLite) ─────────────────────────────────
#
# In Neon-primary mode, every write lands on Neon first (via the router).
# After commit, we mirror the row to local_cache (SQLite) synchronously
# so that subsequent reads from local_cache are immediately consistent.
#
# This is fast (~1ms for a single row on local disk) and keeps the web
# dashboard snappy without ever reading from Neon on page loads.

def _mirror_to_local_cache(sender, pk: int) -> None:
    """
    Copy a single row from default (Neon) → local_cache (SQLite).
    Runs synchronously in the on_commit callback.
    """
    if not _is_neon_primary():
        return  # In offline mode, default IS local_cache — nothing to do.

    if getattr(_MIRROR_ACTIVE, 'value', False):
        return  # Prevent re-entrancy

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
        logger.warning(
            'Local cache mirror failed (%s pk=%s): %s',
            sender.__name__, pk, exc,
        )
    finally:
        _MIRROR_ACTIVE.value = False


def _mirror_delete_to_local_cache(sender, pk: int) -> None:
    """
    Delete a row from local_cache (SQLite) after it was deleted from Neon.
    """
    if not _is_neon_primary():
        return

    if getattr(_MIRROR_ACTIVE, 'value', False):
        return

    _MIRROR_ACTIVE.value = True
    try:
        sender._default_manager.using('local_cache').filter(pk=pk).delete()
    except Exception as exc:
        logger.warning(
            'Local cache mirror-delete failed (%s pk=%s): %s',
            sender.__name__, pk, exc,
        )
    finally:
        _MIRROR_ACTIVE.value = False


# ── On-commit orchestrator ─────────────────────────────────────────────

def _on_commit_save(sender, pk, table, row_data):
    """
    Fired after a successful commit on default (Neon).
    1. Mirror to local_cache (fast, synchronous).
    2. Broadcast to all WS clients (web + mobile).
    """
    _mirror_to_local_cache(sender, pk)
    broadcast_data_changed(table, 'upsert', [row_data])


def _on_commit_delete(sender, pk, table):
    """
    Fired after a successful delete commit on default (Neon).
    1. Mirror delete to local_cache.
    2. Broadcast to all WS clients.
    """
    _mirror_delete_to_local_cache(sender, pk)
    broadcast_data_changed(table, 'delete', [{'id': pk}])


# ── Signal receivers ───────────────────────────────────────────────────

@receiver(post_save)
def on_model_save(sender, instance, using, **kwargs):
    """Mirror saves from default → local_cache and broadcast."""
    if using != 'default':
        return
    if sender._meta.app_label not in SYNCED_APP_LABELS:
        return
    if getattr(_MIRROR_ACTIVE, 'value', False):
        return

    # Capture the row data NOW while the instance is still in memory.
    pk, table = instance.pk, sender._meta.db_table
    row_data = _instance_to_dict(instance)

    db_transaction.on_commit(
        lambda: _on_commit_save(sender, pk, table, row_data),
        using='default',
    )


@receiver(post_delete)
def on_model_delete(sender, instance, using, **kwargs):
    """Mirror deletes from default → local_cache and broadcast."""
    if using != 'default':
        return
    if sender._meta.app_label not in SYNCED_APP_LABELS:
        return
    if getattr(_MIRROR_ACTIVE, 'value', False):
        return

    pk, table = instance.pk, sender._meta.db_table
    db_transaction.on_commit(
        lambda: _on_commit_delete(sender, pk, table),
        using='default',
    )
