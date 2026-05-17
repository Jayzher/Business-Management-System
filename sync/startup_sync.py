"""
sync/startup_sync.py — Background incremental sync on server boot.

When the Django server starts in Neon-primary mode, this module runs a
background thread that pulls any rows from Neon that are newer than what's
in local_cache.  This covers the scenario where:

  - The server was offline for hours/days
  - Another server instance wrote to Neon while this one was down
  - Mobile clients pushed data to Neon via the API
  - Direct SQL was run on Neon (migrations, admin fixes)

The sync is INCREMENTAL — it only pulls rows where updated_at > last_sync_time.
On first boot (no last_sync_time recorded), it does a full hydration.

The last_sync_time is stored in local_cache's sync_metadata table so it
persists across server restarts.

This runs in a daemon thread so the server starts accepting requests
immediately.  Pages served during the sync may show slightly stale data
from local_cache, but they'll be refreshed once the sync completes and
the WS broadcast fires.
"""

import logging
import threading
import time

from django.conf import settings

logger = logging.getLogger(__name__)

_sync_thread = None
_sync_started = False


def start_background_sync():
    """
    Kick off the background incremental sync.
    Called from SyncConfig.ready() — safe to call multiple times (idempotent).
    """
    global _sync_thread, _sync_started

    if _sync_started:
        return

    # Only run in Neon-primary mode
    if getattr(settings, 'SYNC_MODE', 'offline') != 'neon_primary':
        return

    # Check if startup sync is enabled
    if not getattr(settings, 'NEON_INITIAL_SYNC', False):
        # Even if disabled, still do a quick staleness check
        _sync_started = True
        _sync_thread = threading.Thread(
            target=_staleness_check,
            daemon=True,
            name='sync-staleness-check',
        )
        _sync_thread.start()
        return

    _sync_started = True
    _sync_thread = threading.Thread(
        target=_run_incremental_sync_delayed,
        daemon=True,
        name='sync-startup-bg',
    )
    _sync_thread.start()
    logger.info('Background startup sync started')


def _run_incremental_sync_delayed():
    """Wrapper that waits for Django to fully initialize before syncing."""
    time.sleep(3)
    _run_incremental_sync()


def _staleness_check():
    """
    Quick check: is local_cache significantly behind Neon?
    If so, log a warning and trigger an incremental sync anyway.
    """
    try:
        # Wait a moment for Django to fully initialize
        time.sleep(3)

        from django.utils import timezone
        from datetime import timedelta

        last_sync = _get_last_sync_time()

        if last_sync is None:
            # Never synced — need a full hydration
            logger.warning(
                'Local cache has never been synced from Neon. '
                'Running full hydration in background...'
            )
            _run_incremental_sync()
            return

        age = timezone.now() - last_sync
        if age > timedelta(minutes=5):
            logger.info(
                'Local cache is %s behind Neon. Running incremental sync...',
                str(age).split('.')[0],
            )
            _run_incremental_sync()
        else:
            logger.debug('Local cache is fresh (last sync %s ago)', str(age).split('.')[0])

    except Exception as exc:
        logger.warning('Staleness check failed: %s', exc)


def _run_incremental_sync():
    """
    Pull rows from Neon → local_cache where updated_at > last_sync_time.
    If last_sync_time is None, does a full hydration (all rows).
    """
    try:
        from django.apps import apps
        from django.db import connections
        from django.utils import timezone
        from sync.signals import SYNCED_APP_LABELS

        last_sync = _get_last_sync_time()
        sync_start = timezone.now()

        logger.info(
            'Incremental sync starting (since=%s)',
            last_sync.isoformat() if last_sync else 'FULL',
        )

        # Get all synced models
        all_models = [
            m for m in apps.get_models()
            if m._meta.app_label in SYNCED_APP_LABELS and m._meta.managed
        ]

        total_synced = 0
        errors = 0

        # Disable FK checks for bulk operations
        with connections['local_cache'].cursor() as cursor:
            cursor.execute('PRAGMA foreign_keys = OFF;')

        for model in all_models:
            try:
                count = _sync_model(model, last_sync)
                if count > 0:
                    total_synced += count
            except Exception as exc:
                errors += 1
                logger.debug(
                    'Sync failed for %s.%s: %s',
                    model._meta.app_label, model._meta.model_name, exc,
                )

        # Re-enable FK checks
        with connections['local_cache'].cursor() as cursor:
            cursor.execute('PRAGMA foreign_keys = ON;')

        # Record the sync time
        _set_last_sync_time(sync_start)

        elapsed = (timezone.now() - sync_start).total_seconds()
        logger.info(
            'Incremental sync complete: %d rows synced, %d errors, %.1fs elapsed',
            total_synced, errors, elapsed,
        )

        # Broadcast a refresh so any connected web clients update
        if total_synced > 0:
            try:
                from sync.signals import broadcast_table_changed
                broadcast_table_changed(['*'])
            except Exception:
                pass

    except Exception as exc:
        logger.error('Background sync failed: %s', exc)


def _sync_model(model, since_dt) -> int:
    """
    Sync a single model from Neon → local_cache.
    Returns the number of rows synced.
    """
    BATCH_SIZE = 500

    # Build queryset
    qs = model._default_manager.using('default').all()

    if since_dt and hasattr(model, 'updated_at'):
        qs = qs.filter(updated_at__gt=since_dt)
    elif since_dt and hasattr(model, 'created_at'):
        qs = qs.filter(created_at__gt=since_dt)
    elif since_dt:
        # Model has no timestamp field — skip incremental, only sync on full
        return 0

    count = qs.count()
    if count == 0:
        return 0

    # For full sync (since_dt is None), clear the table first.
    # FK checks are already disabled by the caller (_run_incremental_sync).
    if since_dt is None:
        from django.db import connections
        try:
            with connections['local_cache'].cursor() as cursor:
                cursor.execute(f'DELETE FROM "{model._meta.db_table}";')
        except Exception:
            pass  # Table might not exist yet

    # Fetch and upsert in batches
    objs = list(qs.iterator(chunk_size=BATCH_SIZE))

    concrete_fields = [
        f for f in sender._meta.concrete_fields if not f.primary_key
    ]
    update_fields = [f.attname for f in concrete_fields]

    # Temporarily disable auto_now/auto_now_add to preserve timestamps
    auto_fields = []
    for field in model._meta.get_fields():
        if hasattr(field, 'auto_now') and field.auto_now:
            field.auto_now = False
            auto_fields.append(('auto_now', field))
        if hasattr(field, 'auto_now_add') and field.auto_now_add:
            field.auto_now_add = False
            auto_fields.append(('auto_now_add', field))

    try:
        for i in range(0, len(objs), BATCH_SIZE):
            batch = objs[i:i + BATCH_SIZE]
            for obj in batch:
                obj._state.adding = True
                obj._state.db = 'local_cache'

            try:
                if update_fields:
                    model._default_manager.using('local_cache').bulk_create(
                        batch,
                        batch_size=BATCH_SIZE,
                        update_conflicts=True,
                        update_fields=update_fields,
                        unique_fields=['id'],
                    )
                else:
                    model._default_manager.using('local_cache').bulk_create(
                        batch,
                        batch_size=BATCH_SIZE,
                        ignore_conflicts=True,
                    )
            except Exception as exc:
                logger.debug('Batch insert failed for %s: %s', model._meta.db_table, exc)
    finally:
        # Restore auto_now / auto_now_add
        for attr, field in auto_fields:
            setattr(field, attr, True)

    return len(objs)


# ── Last sync time persistence ─────────────────────────────────────────
# Stored in local_cache SQLite using a simple key-value approach via
# Django's cache framework or a raw SQL table.

def _ensure_metadata_table():
    """Create the sync_metadata table if it doesn't exist."""
    from django.db import connections
    with connections['local_cache'].cursor() as cursor:
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sync_metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        ''')


def _get_last_sync_time():
    """Get the last successful sync timestamp from local_cache."""
    from django.db import connections
    from django.utils import timezone
    from datetime import datetime

    try:
        _ensure_metadata_table()
        with connections['local_cache'].cursor() as cursor:
            cursor.execute(
                "SELECT value FROM sync_metadata WHERE key = 'last_sync_time'"
            )
            row = cursor.fetchone()
            if row and row[0]:
                # Handle both naive and aware datetime strings
                dt = datetime.fromisoformat(row[0])
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
    except Exception:
        pass
    return None


def _set_last_sync_time(dt):
    """Store the last successful sync timestamp in local_cache."""
    from django.db import connections

    try:
        _ensure_metadata_table()
        with connections['local_cache'].cursor() as cursor:
            # Django's SQLite backend uses %s for parameter placeholders
            cursor.execute(
                "INSERT OR REPLACE INTO sync_metadata (key, value) VALUES (%s, %s)",
                ['last_sync_time', dt.isoformat()],
            )
    except Exception as exc:
        logger.warning('Failed to store last_sync_time: %s', exc)


def get_last_sync_time():
    """Public API: get the last sync time (used by views/diagnostics)."""
    return _get_last_sync_time()
