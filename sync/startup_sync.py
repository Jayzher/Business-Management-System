"""
sync/startup_sync.py — Background changelog-based sync on server boot.

When the Django server starts in Neon-primary mode, this module runs a
background thread that pulls changes from Neon's NeonChangeLog that
haven't been applied to local_cache yet.

This covers the scenario where:
  - The server was offline for hours/days
  - Another server/device wrote to Neon while this one was down
  - Mobile clients pushed data to Neon via the API
  - Direct SQL was run on Neon (migrations, admin fixes)

The sync is CHANGELOG-BASED:
  1. Read the last-synced changelog ID from local_cache (sync_metadata table).
  2. Fetch all NeonChangeLog entries with id > last_synced_id from Neon.
  3. Replay those changes (upserts/deletes) to local_cache.
  4. Update the checkpoint.

If no checkpoint exists (first boot or corrupted), falls back to a full
hydration (copies all rows from Neon).

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
    Kick off the background changelog-based sync.
    Called from SyncConfig.ready() — safe to call multiple times (idempotent).
    """
    global _sync_thread, _sync_started

    if _sync_started:
        return

    # Only run in Neon-primary mode
    if getattr(settings, 'SYNC_MODE', 'offline') != 'neon_primary':
        return

    _sync_started = True
    _sync_thread = threading.Thread(
        target=_run_changelog_sync_delayed,
        daemon=True,
        name='sync-startup-changelog',
    )
    _sync_thread.start()
    logger.info('Background changelog sync thread started')


def _run_changelog_sync_delayed():
    """Wrapper that waits for Django to fully initialize before syncing."""
    time.sleep(3)

    # If a foreground long-transaction is holding local_cache (e.g. the
    # resync_inventory management command — see background_sync.pause_worker),
    # wait for it to finish first. Without this, this thread's own bulk
    # writes/hydration race that transaction for SQLite's single write lock
    # regardless of which one started first, since this 3s timer is
    # independent of when a foreground command begins.
    try:
        from sync.background_sync import _pause_event
        deadline = time.time() + 300
        while _pause_event.is_set() and time.time() < deadline:
            time.sleep(0.25)
    except Exception:
        pass

    _run_changelog_sync()


def _run_changelog_sync():
    """
    Main sync logic:
      1. Read last-synced changelog ID from local_cache.
      2. If no checkpoint exists, do a full hydration then set checkpoint.
      3. Otherwise, fetch NeonChangeLog entries > checkpoint and replay them.

    Sets _SYNC_IN_PROGRESS flag to prevent signal handlers from racing
    with the sync thread on local_cache writes.
    """
    try:
        from django.apps import apps
        from django.db import connections
        from django.utils import timezone
        from sync.signals import set_sync_in_progress

        last_log_id = _get_last_synced_log_id()
        sync_start = timezone.now()

        # Set flag so signal handlers skip local_cache mirroring during sync
        set_sync_in_progress(True)

        try:
            if last_log_id is None:
                # No checkpoint — first boot or reset.
                if not getattr(settings, 'NEON_INITIAL_SYNC', False):
                    logger.info(
                        'No sync checkpoint and NEON_INITIAL_SYNC=false. '
                        'Skipping full hydration — run `hydrate_local_cache` manually.'
                    )
                    _set_checkpoint_to_latest()
                    return

                logger.info('No sync checkpoint found — running full hydration...')
                failed = _run_full_hydration()
                if failed:
                    logger.error(
                        'Full hydration incomplete (%d model(s) failed) — '
                        'checkpoint left unset, will retry on next sync run.',
                        len(failed),
                    )
                    return
                _set_checkpoint_to_latest()
                _set_last_sync_time(sync_start)
                logger.info('Full hydration complete. Checkpoint set.')
                return

            # We have a checkpoint — pull only the delta from NeonChangeLog
            logger.info('Changelog sync starting (since log_id=%d)', last_log_id)

            # Safety check: if the checkpoint references a log_id that was pruned,
            # we need to fall back to full hydration.
            from sync.models import NeonChangeLog

            changelog_count = NeonChangeLog.objects.using('default').count()

            # TRANSITION SCENARIO: checkpoint is 0 and changelog is empty.
            # This means the changelog system was just deployed but no changes
            # have been logged yet.  Pre-existing Neon data may not be in
            # local_cache.  Do a full hydration to catch up.
            if last_log_id == 0 and changelog_count == 0:
                logger.info(
                    'Checkpoint is 0 and changelog is empty — this is likely '
                    'the first boot after deploying the changelog system. '
                    'Running full hydration to catch pre-existing changes...'
                )
                failed = _run_full_hydration()
                if failed:
                    logger.error(
                        'Full hydration incomplete (%d model(s) failed) — '
                        'checkpoint left unset, will retry on next sync run.',
                        len(failed),
                    )
                    return
                _set_checkpoint_to_latest()
                _set_last_sync_time(sync_start)
                return

            oldest_entry = (
                NeonChangeLog.objects.using('default')
                .order_by('id')
                .values_list('id', flat=True)
                .first()
            )

            if oldest_entry is not None and last_log_id < oldest_entry:
                logger.warning(
                    'Checkpoint log_id=%d is older than the oldest changelog entry (%d). '
                    'Changelog was pruned — falling back to full hydration.',
                    last_log_id, oldest_entry,
                )
                failed = _run_full_hydration()
                if failed:
                    logger.error(
                        'Full hydration incomplete (%d model(s) failed) — '
                        'checkpoint left unset, will retry on next sync run.',
                        len(failed),
                    )
                    return
                _set_checkpoint_to_latest()
                _set_last_sync_time(sync_start)
                return

            total_applied = _replay_changelog_entries(last_log_id)

            elapsed = (timezone.now() - sync_start).total_seconds()
            logger.info(
                'Changelog sync complete: %d changes applied, %.1fs elapsed',
                total_applied, elapsed,
            )

            # Update legacy sync time for backward compat
            _set_last_sync_time(sync_start)

            # Broadcast a refresh so any connected web clients update
            if total_applied > 0:
                try:
                    from sync.signals import broadcast_table_changed
                    broadcast_table_changed(['*'])
                except Exception:
                    pass

        finally:
            # Always clear the flag so normal signal mirroring resumes
            set_sync_in_progress(False)

    except Exception as exc:
        logger.error('Background changelog sync failed: %s', exc)
        # Ensure flag is cleared even on unexpected errors
        try:
            from sync.signals import set_sync_in_progress
            set_sync_in_progress(False)
        except Exception:
            pass


def _replay_changelog_entries(since_log_id: int) -> int:
    """
    Fetch NeonChangeLog entries with id > since_log_id and replay them
    to local_cache.  Returns the number of changes applied.

    DEDUPLICATION: If the same (table, row_pk) appears multiple times in
    the changelog batch, we only apply the LATEST action.  This prevents:
      - Wasted work (updating the same row 10 times)
      - Conflicts (an older upsert overwriting a newer state)
      - Contamination (applying an upsert after a delete for the same row)

    The deduplication is per-batch (500 entries).  Since we always fetch
    the latest state from Neon (not from row_data), even without dedup
    the result would be correct — but dedup makes it faster and cleaner.
    """
    from django.apps import apps
    from django.db import connections

    try:
        from sync.models import NeonChangeLog
    except ImportError:
        logger.error('NeonChangeLog model not available')
        return 0

    BATCH_SIZE = 500
    total_applied = 0
    current_cursor = since_log_id

    # Disable FK checks for bulk operations
    with connections['local_cache'].cursor() as cursor:
        cursor.execute('PRAGMA foreign_keys = OFF;')

    try:
        while True:
            # Fetch next batch of changelog entries from Neon
            entries = list(
                NeonChangeLog.objects.using('default')
                .filter(id__gt=current_cursor)
                .order_by('id')[:BATCH_SIZE]
            )

            if not entries:
                break

            # ── Deduplicate: keep only the LATEST entry per (table, row_pk) ──
            # Since entries are ordered by id ASC, later entries override earlier.
            seen = {}  # (db_table, row_pk) → entry
            for entry in entries:
                key = (entry.db_table, entry.row_pk)
                seen[key] = entry  # last one wins

            # Apply deduplicated entries
            for entry in seen.values():
                try:
                    _apply_changelog_entry(entry, apps)
                    total_applied += 1
                except Exception as exc:
                    # Record the failure instead of silently skipping it — a
                    # debug-level log line was easy to lose, and the checkpoint
                    # still advances past this entry below (a stuck row would
                    # otherwise permanently stall replay of everything after
                    # it). `retry_changelog_failures` re-attempts these against
                    # Neon's current state; the sync diagnostics endpoint
                    # surfaces the count so this doesn't go unnoticed again.
                    logger.error(
                        'Failed to apply changelog entry #%d (%s %s#%d): %s',
                        entry.pk, entry.action, entry.db_table, entry.row_pk, exc,
                    )
                    _record_replay_failure(entry, exc)

            # Advance cursor to the last entry in the batch (not just deduped)
            current_cursor = entries[-1].pk

            # Update checkpoint after each batch so we don't re-process on crash
            _set_last_synced_log_id(current_cursor)

    finally:
        # Re-enable FK checks
        with connections['local_cache'].cursor() as cursor:
            cursor.execute('PRAGMA foreign_keys = ON;')

    return total_applied


def _record_replay_failure(entry, exc):
    """
    Upsert a ChangelogReplayFailure row for this (db_table, row_pk) so a
    failed replay is visible and retryable instead of just a debug log
    line. Never raises — recording the failure must not itself break the
    replay loop.
    """
    try:
        from sync.models import ChangelogReplayFailure
        from django.utils import timezone as tz

        now = tz.now()
        obj, created = ChangelogReplayFailure.objects.using('local_cache').get_or_create(
            db_table=entry.db_table,
            row_pk=entry.row_pk,
            defaults={
                'changelog_id': entry.pk,
                'action': entry.action,
                'app_label': entry.app_label,
                'model_name': entry.model_name,
                'error_message': str(exc)[:2000],
                'first_failed_at': now,
                'last_failed_at': now,
                'attempts': 1,
            },
        )
        if not created:
            obj.changelog_id = entry.pk
            obj.action = entry.action
            obj.error_message = str(exc)[:2000]
            obj.last_failed_at = now
            obj.attempts += 1
            obj.save(update_fields=[
                'changelog_id', 'action', 'error_message', 'last_failed_at', 'attempts',
            ])
    except Exception as record_exc:
        logger.error('Failed to record changelog replay failure: %s', record_exc)


def _apply_changelog_entry(entry, apps):
    """Apply a single NeonChangeLog entry to local_cache.

    CONFLICT PREVENTION:
      - For upserts: we ALWAYS fetch the current row from Neon (not from
        row_data in the changelog).  This guarantees local_cache gets the
        latest state even if multiple changes happened to the same row.
        Neon is the single source of truth — local_cache is just a mirror.

      - For deletes: we delete from local_cache unconditionally.  If the
        row doesn't exist locally, the delete is a no-op (safe).

      - If a row was upserted then deleted (or vice versa), the deduplication
        in _replay_changelog_entries ensures only the LATEST action is applied.
        If the latest action is 'delete', the row is removed.  If 'upsert',
        we fetch from Neon — if it's gone there too, we delete locally.
    """
    try:
        model = apps.get_model(entry.app_label, entry.model_name)
    except LookupError:
        logger.debug(
            'Model %s.%s not found, skipping changelog entry #%d',
            entry.app_label, entry.model_name, entry.pk,
        )
        return

    if entry.action == 'delete':
        # Delete from local_cache — idempotent (no error if row doesn't exist)
        model._default_manager.using('local_cache').filter(pk=entry.row_pk).delete()

    elif entry.action == 'upsert':
        # ALWAYS fetch the current row from Neon (authoritative source).
        # This prevents stale row_data from contaminating local_cache when
        # multiple changes happened to the same row between syncs.
        obj = model._default_manager.using('default').filter(pk=entry.row_pk).first()
        if obj is None:
            # Row was deleted on Neon after the changelog entry was created.
            # Clean up local_cache to stay consistent.
            model._default_manager.using('local_cache').filter(pk=entry.row_pk).delete()
            return

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
            obj._state.adding = True
            obj._state.db = 'local_cache'

            concrete_fields = [
                f for f in model._meta.concrete_fields if not f.primary_key
            ]
            update_fields = [f.attname for f in concrete_fields]

            if update_fields:
                model._default_manager.using('local_cache').bulk_create(
                    [obj],
                    update_conflicts=True,
                    update_fields=update_fields,
                    unique_fields=['id'],
                )
            else:
                model._default_manager.using('local_cache').bulk_create(
                    [obj], ignore_conflicts=True,
                )
        finally:
            # Restore auto_now / auto_now_add
            for attr, field in auto_fields:
                setattr(field, attr, True)


def _run_full_hydration():
    """
    Full copy of all synced models from Neon → local_cache.
    Used on first boot when no changelog checkpoint exists.

    Each model is wiped (DELETE FROM) and refilled independently — if
    copying one model raises partway through (a lock, a transient error),
    that table is left wiped but not refilled while every other table,
    including ones with FKs pointing into it, hydrates fine. That used to
    fail silently (debug-level log, keep going) and still let the caller
    advance the sync checkpoint past it — the exact same kind of
    orphaned-parent corruption a prior session had to repair by hand, just
    at table granularity instead of row granularity.

    Returns a list of "app_label.model_name" strings for models that
    failed to hydrate. Callers must NOT advance the sync checkpoint when
    this is non-empty — leaving the checkpoint unset makes the next sync
    run retry the full hydration from scratch instead of settling into a
    silently half-populated state forever.
    """
    from django.apps import apps
    from django.db import connections
    from sync.signals import SYNCED_APP_LABELS

    BATCH_SIZE = 500

    all_models = [
        m for m in apps.get_models()
        if m._meta.app_label in SYNCED_APP_LABELS and m._meta.managed
    ]

    # Disable FK checks for bulk load
    with connections['local_cache'].cursor() as cursor:
        cursor.execute('PRAGMA foreign_keys = OFF;')

    total_copied = 0
    failed_models = []

    for model in all_models:
        try:
            count = model._default_manager.using('default').count()
            if count == 0:
                continue

            # Clear local_cache table
            try:
                with connections['local_cache'].cursor() as cursor:
                    cursor.execute(f'DELETE FROM "{model._meta.db_table}";')
            except Exception:
                pass  # Table might not exist yet

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
                objs = list(model._default_manager.using('default').all())
                for obj in objs:
                    obj._state.adding = True
                    obj._state.db = 'local_cache'

                concrete_fields = [
                    f for f in model._meta.concrete_fields if not f.primary_key
                ]
                update_fields = [f.attname for f in concrete_fields]

                for i in range(0, len(objs), BATCH_SIZE):
                    batch = objs[i:i + BATCH_SIZE]
                    if update_fields:
                        model._default_manager.using('local_cache').bulk_create(
                            batch, batch_size=BATCH_SIZE,
                            update_conflicts=True,
                            update_fields=update_fields,
                            unique_fields=['id'],
                        )
                    else:
                        model._default_manager.using('local_cache').bulk_create(
                            batch, batch_size=BATCH_SIZE, ignore_conflicts=True,
                        )
                total_copied += count
            finally:
                for attr, field in auto_fields:
                    setattr(field, attr, True)

        except Exception as exc:
            failed_models.append(f'{model._meta.app_label}.{model._meta.model_name}')
            logger.error(
                'Full hydration failed for %s.%s: %s',
                model._meta.app_label, model._meta.model_name, exc,
            )

    # Re-enable FK checks
    with connections['local_cache'].cursor() as cursor:
        cursor.execute('PRAGMA foreign_keys = ON;')

    if failed_models:
        logger.error(
            'Full hydration: %d rows copied, but %d model(s) FAILED and were '
            'left wiped/incomplete: %s. Checkpoint will not advance so the '
            'next sync run retries.',
            total_copied, len(failed_models), ', '.join(failed_models),
        )
    else:
        logger.info('Full hydration: %d rows copied to local_cache', total_copied)

    return failed_models


def _set_checkpoint_to_latest():
    """Set the sync checkpoint to the latest NeonChangeLog entry ID on Neon."""
    try:
        from sync.models import NeonChangeLog
        latest = (
            NeonChangeLog.objects.using('default')
            .order_by('-id')
            .values_list('id', flat=True)
            .first()
        )
        # If no changelog entries exist yet, set to 0
        _set_last_synced_log_id(latest or 0)
    except Exception as exc:
        logger.warning('Failed to set checkpoint to latest: %s', exc)
        _set_last_synced_log_id(0)


# ── Checkpoint persistence (sync_metadata table in local_cache) ────────

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


def _get_last_synced_log_id() -> int | None:
    """Get the last-synced NeonChangeLog ID from local_cache.

    Returns None if no checkpoint has been set (first boot).
    Returns 0 if explicitly set to 0 (full hydration done, no log entries yet).
    """
    from django.db import connections

    try:
        _ensure_metadata_table()
        with connections['local_cache'].cursor() as cursor:
            cursor.execute(
                "SELECT value FROM sync_metadata WHERE key = 'last_synced_log_id'"
            )
            row = cursor.fetchone()
            if row and row[0]:
                return int(row[0])
    except Exception:
        pass
    return None


def _set_last_synced_log_id(log_id: int):
    """Store the last-synced NeonChangeLog ID in local_cache."""
    from django.db import connections

    try:
        _ensure_metadata_table()
        with connections['local_cache'].cursor() as cursor:
            cursor.execute(
                "INSERT OR REPLACE INTO sync_metadata (key, value) VALUES (%s, %s)",
                ['last_synced_log_id', str(log_id)],
            )
    except Exception as exc:
        logger.warning('Failed to store last_synced_log_id: %s', exc)


def _get_last_sync_time():
    """Get the last successful sync timestamp from local_cache (legacy)."""
    from django.db import connections
    from django.utils import timezone
    from datetime import datetime, timezone as dt_timezone

    try:
        _ensure_metadata_table()
        with connections['local_cache'].cursor() as cursor:
            cursor.execute(
                "SELECT value FROM sync_metadata WHERE key = 'last_sync_time'"
            )
            row = cursor.fetchone()
            if row and row[0]:
                dt = datetime.fromisoformat(row[0])
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=dt_timezone.utc)
                return dt
    except Exception:
        pass
    return None


def _set_last_sync_time(dt):
    """Store the last successful sync timestamp in local_cache (legacy)."""
    from django.db import connections

    try:
        _ensure_metadata_table()
        with connections['local_cache'].cursor() as cursor:
            cursor.execute(
                "INSERT OR REPLACE INTO sync_metadata (key, value) VALUES (%s, %s)",
                ['last_sync_time', dt.isoformat()],
            )
    except Exception as exc:
        logger.warning('Failed to store last_sync_time: %s', exc)


def get_last_sync_time():
    """Public API: get the last sync time (used by views/diagnostics)."""
    return _get_last_sync_time()


def get_last_synced_log_id():
    """Public API: get the last-synced changelog ID (used by views/diagnostics)."""
    return _get_last_synced_log_id()
