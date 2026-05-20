"""
sync/background_sync.py — Background thread for async post-commit sync work.

THE PROBLEM:
  Every save/delete to Neon triggers 3 synchronous operations on_commit:
    1. Mirror to local_cache (read from Neon + write to SQLite)
    2. Log to NeonChangeLog (write to Neon)
    3. WebSocket broadcast
  This adds ~50-150ms per write, making forms with multiple objects feel slow.

THE FIX:
  A background worker thread with a queue.  The on_commit callback just
  enqueues a lightweight task dict and returns immediately (~0ms).
  The worker thread processes tasks in order, batching where possible.

  The user's HTTP response returns as soon as the Neon write commits.
  The mirror/changelog/broadcast happen in the background within milliseconds.

GUARANTEES:
  - Tasks are processed in FIFO order (preserves causality).
  - If the worker crashes, tasks are lost — but the changelog sync on next
    boot will catch up (the Neon write already succeeded).
  - The worker is a daemon thread — it dies when the server stops.
  - Batching: multiple tasks for the same table are coalesced into fewer
    DB operations when the queue has a backlog.
"""

import logging
import queue
import threading
import time

from django.conf import settings

logger = logging.getLogger(__name__)

# The task queue — unbounded, FIFO
_task_queue = queue.Queue()

# Worker thread reference
_worker_thread = None
_worker_started = False


def start_background_worker():
    """Start the background sync worker thread (idempotent)."""
    global _worker_thread, _worker_started

    if _worker_started:
        return

    if getattr(settings, 'SYNC_MODE', 'offline') != 'neon_primary':
        return

    _worker_started = True
    _worker_thread = threading.Thread(
        target=_worker_loop,
        daemon=True,
        name='sync-bg-worker',
    )
    _worker_thread.start()
    logger.debug('Background sync worker started')


def enqueue_save(sender, pk: int, table: str, app_label: str,
                 model_name: str, row_data: dict):
    """Enqueue a post-commit save task (non-blocking, ~0ms)."""
    _task_queue.put({
        'type': 'save',
        'sender': sender,
        'pk': pk,
        'table': table,
        'app_label': app_label,
        'model_name': model_name,
        'row_data': row_data,
        'enqueued_at': time.time(),
    })


def enqueue_delete(sender, pk: int, table: str, app_label: str,
                   model_name: str):
    """Enqueue a post-commit delete task (non-blocking, ~0ms)."""
    _task_queue.put({
        'type': 'delete',
        'sender': sender,
        'pk': pk,
        'table': table,
        'app_label': app_label,
        'model_name': model_name,
        'enqueued_at': time.time(),
    })


def get_queue_size() -> int:
    """Return the current number of pending tasks (for diagnostics)."""
    return _task_queue.qsize()


# ── Worker loop ────────────────────────────────────────────────────────

def _worker_loop():
    """
    Main worker loop.  Processes tasks from the queue one at a time.
    Batches consecutive tasks for the same operation when possible.

    IMPORTANT: Each batch is processed in its own short transaction.
    After each batch, we close the DB connections to release any locks.
    This prevents the background worker from holding SQLite locks that
    would block user requests.
    """
    while True:
        try:
            # Block until a task is available (with timeout for graceful shutdown)
            task = _task_queue.get(timeout=5.0)
        except queue.Empty:
            continue

        batch = [task]
        try:
            # Drain additional tasks that arrived while we were processing
            # (batch optimization — reduces DB round-trips under load)
            # Keep batch size small (10) to minimize SQLite lock duration
            try:
                while len(batch) < 10:  # Max batch size (reduced from 50)
                    extra = _task_queue.get_nowait()
                    batch.append(extra)
            except queue.Empty:
                pass

            _process_batch(batch)

        except Exception as exc:
            logger.warning('Background sync worker error: %s', exc)
        finally:
            # Mark all tasks as done
            for _ in batch:
                _task_queue.task_done()

            # Close DB connections after each batch to release locks.
            # This is critical — without this, the background thread holds
            # the SQLite connection open, which can block user writes even
            # in WAL mode (if a write transaction is left open).
            try:
                from django.db import connections
                for alias in ('local_cache', 'default'):
                    try:
                        connections[alias].close()
                    except Exception:
                        pass
            except Exception:
                pass


def _process_batch(batch: list):
    """Process a batch of tasks efficiently."""
    from sync.signals import (
        _mirror_to_local_cache, _mirror_delete_to_local_cache,
        _log_to_neon_changelog, broadcast_data_changed,
        is_fallback_active, _SYNC_IN_PROGRESS,
    )

    # Group by type for efficient processing
    saves = [t for t in batch if t['type'] == 'save']
    deletes = [t for t in batch if t['type'] == 'delete']
    neon_soft_deletes = [t for t in batch if t['type'] == 'neon_soft_delete']
    neon_hard_deletes = [t for t in batch if t['type'] == 'neon_hard_delete']

    # ── Process saves (push local_cache writes to Neon) ──────────────────
    if saves:
        # Deduplicate: if the same (table, pk) appears multiple times,
        # only process the LAST one (most recent state)
        seen = {}
        for task in saves:
            key = (task['table'], task['pk'])
            seen[key] = task
        unique_saves = list(seen.values())

        for task in unique_saves:
            try:
                # 1. Push to Neon (upsert)
                _push_upsert_to_neon(task)

                # 2. Log to NeonChangeLog
                _log_to_neon_changelog(
                    'upsert', task['table'], task['app_label'],
                    task['model_name'], task['pk'], task['row_data'],
                )

                # 3. Broadcast via WebSocket
                broadcast_data_changed(task['table'], 'upsert', [task['row_data']])

            except Exception as exc:
                logger.debug(
                    'BG push to Neon failed (%s pk=%s): %s — queuing to outbox',
                    task['table'], task['pk'], exc,
                )
                # Queue to outbox for retry when Neon is back
                _queue_failed_to_outbox(task, 'upsert', exc)
                # Still broadcast locally so connected clients see the change
                broadcast_data_changed(task['table'], 'upsert', [task['row_data']])

    # ── Process deletes (push local_cache deletes to Neon) ─────────────
    if deletes:
        seen = {}
        for task in deletes:
            key = (task['table'], task['pk'])
            seen[key] = task
        unique_deletes = list(seen.values())

        for task in unique_deletes:
            try:
                # 1. Delete from Neon
                _push_delete_to_neon(task)

                # 2. Log to NeonChangeLog
                _log_to_neon_changelog(
                    'delete', task['table'], task['app_label'],
                    task['model_name'], task['pk'], None,
                )

                # 3. Broadcast via WebSocket
                broadcast_data_changed(
                    task['table'], 'delete', [{'id': task['pk']}],
                )

            except Exception as exc:
                logger.debug(
                    'BG delete push to Neon failed (%s pk=%s): %s — queuing to outbox',
                    task['table'], task['pk'], exc,
                )
                _queue_failed_to_outbox(task, 'delete', exc)
                broadcast_data_changed(
                    task['table'], 'delete', [{'id': task['pk']}],
                )

    # ── Process local-first soft deletes (legacy — kept for compatibility) ─
    if neon_soft_deletes:
        seen = {}
        for task in neon_soft_deletes:
            key = (task['table'], task['pk'])
            seen[key] = task

        for task in seen.values():
            try:
                _apply_neon_soft_delete(task)
            except Exception as exc:
                logger.warning(
                    'BG neon_soft_delete failed (%s pk=%s): %s',
                    task['table'], task['pk'], exc,
                )
                _queue_failed_to_outbox(task, 'upsert', exc)

    # ── Process local-first hard deletes (legacy — kept for compatibility) ─
    if neon_hard_deletes:
        seen = {}
        for task in neon_hard_deletes:
            key = (task['table'], task['pk'])
            seen[key] = task

        for task in seen.values():
            try:
                _apply_neon_hard_delete(task)
            except Exception as exc:
                logger.warning(
                    'BG neon_hard_delete failed (%s pk=%s): %s',
                    task['table'], task['pk'], exc,
                )
                _queue_failed_to_outbox(task, 'delete', exc)


def _push_upsert_to_neon(task):
    """Push a row to Neon using the serialized row_data from the task.
    
    This avoids reading from local_cache (which could cause lock contention).
    The row_data was captured at the time of the local_cache write, so it's
    already the correct state to push to Neon.
    
    IMPORTANT: We use bulk_create with update_conflicts=True instead of
    update_or_create to avoid triggering signals and to preserve timestamps
    from local_cache.
    """
    sender = task['sender']
    pk = task['pk']
    row_data = task.get('row_data')
    
    if not row_data:
        # No row data in task — skip (shouldn't happen)
        logger.debug('No row_data in task for %s pk=%s', sender.__name__, pk)
        return
    
    # Reconstruct the model instance from row_data
    obj = sender(**row_data)
    obj.pk = pk
    obj._state.adding = True
    obj._state.db = 'default'
    
    concrete_fields = [
        f for f in sender._meta.concrete_fields if not f.primary_key
    ]
    update_fields = [f.attname for f in concrete_fields]

    # Use bulk_create with update_conflicts to bypass auto_now behavior
    # This preserves the exact timestamps from local_cache
    if update_fields:
        sender._default_manager.using('default').bulk_create(
            [obj],
            update_conflicts=True,
            update_fields=update_fields,
            unique_fields=['id'],
        )
    else:
        sender._default_manager.using('default').bulk_create(
            [obj], ignore_conflicts=True,
        )


def _push_delete_to_neon(task):
    """Delete a row from Neon."""
    sender = task['sender']
    pk = task['pk']
    # Use all_objects to bypass soft-delete manager
    mgr = getattr(sender, 'all_objects', sender._default_manager)
    mgr.using('default').filter(pk=pk).delete()


def _apply_neon_soft_delete(task):
    """Apply a soft-delete (UPDATE is_active=False) to Neon."""
    from sync.signals import _log_to_neon_changelog, _instance_to_dict
    from django.utils import timezone as tz

    sender = task['sender']
    pk = task['pk']

    # Update on Neon
    updated = sender.all_objects.using('default').filter(pk=pk).update(
        is_active=False, updated_at=tz.now()
    )

    if updated:
        # Log to changelog so other devices catch up
        obj = sender.all_objects.using('default').filter(pk=pk).first()
        if obj:
            row_data = _instance_to_dict(obj)
            _log_to_neon_changelog(
                'upsert', task['table'], task['app_label'],
                task['model_name'], pk, row_data,
            )


def _apply_neon_hard_delete(task):
    """Apply a hard-delete (DELETE) to Neon."""
    from sync.signals import _log_to_neon_changelog

    sender = task['sender']
    pk = task['pk']

    # Delete from Neon
    sender._default_manager.using('default').filter(pk=pk).delete()

    # Log to changelog
    _log_to_neon_changelog(
        'delete', task['table'], task['app_label'],
        task['model_name'], pk, None,
    )


def _queue_failed_to_outbox(task, action, exc):
    """If the Neon push fails, queue it to SyncOutbox for later retry."""
    try:
        from sync.models import SyncOutbox
        SyncOutbox.objects.using('local_cache').create(
            action=action,
            db_table=task['table'],
            app_label=task['app_label'],
            model_name=task['model_name'],
            row_pk=task['pk'],
            row_data=task.get('row_data'),
        )
        logger.info('Queued failed Neon push to outbox: %s %s#%d',
                    action, task['table'], task['pk'])
    except Exception as outbox_exc:
        logger.error('Failed to queue to outbox (%s %s#%d): %s',
                     action, task['table'], task['pk'], outbox_exc)
