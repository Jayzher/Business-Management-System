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
    """
    while True:
        try:
            # Block until a task is available (with timeout for graceful shutdown)
            task = _task_queue.get(timeout=5.0)
        except queue.Empty:
            continue

        try:
            # Drain additional tasks that arrived while we were processing
            # (batch optimization — reduces DB round-trips under load)
            batch = [task]
            try:
                while len(batch) < 50:  # Max batch size
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

    # ── Process saves ──────────────────────────────────────────────────
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
                # 1. Mirror to local_cache
                if not is_fallback_active() and not _SYNC_IN_PROGRESS.is_set():
                    _mirror_to_local_cache(task['sender'], task['pk'])

                # 2. Log to NeonChangeLog
                _log_to_neon_changelog(
                    'upsert', task['table'], task['app_label'],
                    task['model_name'], task['pk'], task['row_data'],
                )

                # 3. Broadcast via WebSocket
                broadcast_data_changed(task['table'], 'upsert', [task['row_data']])

            except Exception as exc:
                logger.debug(
                    'BG save failed (%s pk=%s): %s',
                    task['table'], task['pk'], exc,
                )

    # ── Process deletes (post-commit mirror from Neon signals) ─────────
    if deletes:
        # Deduplicate deletes too
        seen = {}
        for task in deletes:
            key = (task['table'], task['pk'])
            seen[key] = task
        unique_deletes = list(seen.values())

        for task in unique_deletes:
            try:
                # 1. Mirror delete to local_cache
                if not is_fallback_active() and not _SYNC_IN_PROGRESS.is_set():
                    _mirror_delete_to_local_cache(task['sender'], task['pk'])

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
                    'BG delete failed (%s pk=%s): %s',
                    task['table'], task['pk'], exc,
                )

    # ── Process local-first soft deletes (apply to Neon) ───────────────
    if neon_soft_deletes:
        seen = {}
        for task in neon_soft_deletes:
            key = (task['table'], task['pk'])
            seen[key] = task
        unique_neon_soft = list(seen.values())

        for task in unique_neon_soft:
            try:
                _apply_neon_soft_delete(task)
            except Exception as exc:
                logger.warning(
                    'BG neon_soft_delete failed (%s pk=%s): %s',
                    task['table'], task['pk'], exc,
                )
                # Queue to outbox for retry if Neon is unreachable
                _queue_failed_delete_to_outbox(task, 'upsert', exc)

    # ── Process local-first hard deletes (apply to Neon) ───────────────
    if neon_hard_deletes:
        seen = {}
        for task in neon_hard_deletes:
            key = (task['table'], task['pk'])
            seen[key] = task
        unique_neon_hard = list(seen.values())

        for task in unique_neon_hard:
            try:
                _apply_neon_hard_delete(task)
            except Exception as exc:
                logger.warning(
                    'BG neon_hard_delete failed (%s pk=%s): %s',
                    task['table'], task['pk'], exc,
                )
                # Queue to outbox for retry
                _queue_failed_delete_to_outbox(task, 'delete', exc)


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


def _queue_failed_delete_to_outbox(task, action, exc):
    """If the Neon delete fails, queue it to SyncOutbox for later retry."""
    try:
        from sync.models import SyncOutbox
        SyncOutbox.objects.using('local_cache').create(
            action=action,
            db_table=task['table'],
            app_label=task['app_label'],
            model_name=task['model_name'],
            row_pk=task['pk'],
            row_data=None,
        )
        logger.info('Queued failed delete to outbox: %s#%d', task['table'], task['pk'])
    except Exception as outbox_exc:
        logger.error('Failed to queue delete to outbox (%s#%d): %s',
                     task['table'], task['pk'], outbox_exc)
