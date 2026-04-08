"""
sync/signals.py — Post-save hooks for event-driven cross-DB sync.

When any web-admin model save hits the default (SQLite) database:
  1. A background thread asynchronously writes the same row to Neon so
     mobile clients that read Neon directly can see the change.
  2. A Pusher event is triggered on channel 'sync', event 'table-changed',
     with payload {"tables": [<db_table_name>]}.  Mobile clients subscribed
     to that channel know to re-pull only that specific table from Neon.

The _NEON_WRITE_ACTIVE thread-local prevents re-entrancy if the async
thread itself triggers a post_save (e.g. via bulk_create).
"""

import logging
import threading

from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)

_NEON_WRITE_ACTIVE = threading.local()

SYNCED_APP_LABELS = {
    'core', 'accounts', 'catalog', 'partners', 'warehouses',
    'inventory', 'procurement', 'sales', 'audit', 'pricing',
    'pos', 'services', 'cashflow',
}


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


def broadcast_table_changed(tables: list[str]) -> None:
    """
    Trigger a Pusher event on channel 'sync', event 'table-changed'.
    Payload: {"tables": [<db_table_name>, ...]}.
    Fails silently when Pusher credentials are missing or unavailable.
    """
    client = _get_pusher()
    if client is None:
        return
    try:
        client.trigger('sync', 'table-changed', {'tables': tables})
        logger.debug('Pusher triggered table-changed: %s', tables)
    except Exception as exc:
        logger.debug('Pusher trigger skipped (%s): %s', tables, exc)


def _write_to_neon_async(sender, pk: int) -> None:
    """
    Spawn a daemon thread that upserts the record identified by *pk* into the
    'neon' database alias.  Uses INSERT … ON CONFLICT (id) DO UPDATE so it
    handles both new inserts and updates transparently.
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
        except Exception as exc:
            logger.debug(
                'Neon write-through skipped (%s pk=%s): %s', sender.__name__, pk, exc
            )
        finally:
            _NEON_WRITE_ACTIVE.value = False

    threading.Thread(target=_worker, daemon=True, name=f'neon-wt-{sender.__name__}').start()


@receiver(post_save)
def on_model_save(sender, instance, using, **kwargs):
    if using != 'default':
        return
    if sender._meta.app_label not in SYNCED_APP_LABELS:
        return
    if getattr(_NEON_WRITE_ACTIVE, 'value', False):
        return

    table = sender._meta.db_table
    _write_to_neon_async(sender, instance.pk)
    broadcast_table_changed([table])
