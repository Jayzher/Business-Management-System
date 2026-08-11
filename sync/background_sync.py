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
  - The in-memory queue itself is NOT durable — a process crash/restart
    loses whatever's still sitting in it. What makes this safe is that
    enqueue_save()/enqueue_delete() ALSO write a durable SyncOutbox row
    (a fast local SQLite write, not a network call) before returning, so
    a lost in-memory task always has a durable record behind it. The
    worker deletes that row once the Neon push actually succeeds; if it
    never gets that far, the row is left PENDING and gets picked up by
    the automatic drain on the next server boot (see sync/apps.py) or by
    `manage.py drain_sync_outbox`. Without this, a task lost mid-queue
    would silently never reach Neon or NeonChangeLog — the row would sit
    correctly in local_cache forever while every other device, and the
    cloud dashboard, never learned it existed.
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

# Pause support — lets a long-lived foreground transaction (e.g. the
# resync_inventory management command holding one transaction across
# thousands of rows) get exclusive use of the SQLite connection instead of
# fighting this thread for the write lock on every batch.
_pause_event = threading.Event()
_idle_event = threading.Event()
_idle_event.set()  # idle until the first task arrives

# Separate pause/idle pair for an actively-running `drain_sync_outbox` loop.
# Kept independent from _pause_event/_idle_event above because drain itself
# calls pause_live_worker_only() (which only touches _pause_event) to pause
# the live worker while IT writes — sharing one flag would make the drain
# pause itself. A foreground bulk-write operation calls the full
# pause_worker() below, which sets BOTH, so it also gets exclusive access
# against a drain that's mid-run (see project memory: a reintroduced
# local_cache read in drain_sync_outbox._replay_upsert plus this missing
# coordination caused repeated "database is locked" errors on
# supplier-catalog sync, 2026-08-11).
_drain_pause_event = threading.Event()
_drain_idle_event = threading.Event()
_drain_idle_event.set()  # idle until a drain loop actually starts


def pause_worker(timeout=10.0):
    """Pause ALL local_cache-writing background activity — the live
    per-save worker AND any actively-running `drain_sync_outbox` loop —
    before a long-lived foreground transaction elsewhere.

    Blocks until any in-flight worker batch finishes (batches are capped at
    10 tasks and close their connections immediately after, so this is
    normally near-instant) and until the drain loop reaches a pause point
    between entries. Also waits for the separate startup changelog-sync
    thread (sync/startup_sync.py) to finish if it's mid-run — that thread
    does its own bulk writes/hydration to local_cache independent of this
    task queue, and races the same SQLite write lock (e.g. right after a
    server restart, when it fires ~3s after boot).

    Safe to call even if none of these background activities are running.
    Returns True once all are confirmed idle, False on timeout (the caller
    should treat that as "proceed cautiously" rather than fail).
    """
    _pause_event.set()
    _drain_pause_event.set()
    worker_idle = _idle_event.wait(timeout=timeout)
    drain_idle = _drain_idle_event.wait(timeout=timeout)

    try:
        from sync.signals import is_sync_in_progress
        deadline = time.time() + timeout
        while is_sync_in_progress() and time.time() < deadline:
            time.sleep(0.25)
        startup_sync_idle = not is_sync_in_progress()
    except Exception:
        startup_sync_idle = True  # module unavailable — nothing to wait for

    return worker_idle and drain_idle and startup_sync_idle


def pause_live_worker_only(timeout=10.0):
    """Pause just the live per-save worker (not any active drain) — used
    internally by drain_sync_outbox, which cannot use the full
    pause_worker() on itself without self-deadlocking against
    _drain_pause_event."""
    _pause_event.set()
    return _idle_event.wait(timeout=timeout)


def resume_live_worker_only():
    _pause_event.clear()


def drain_wait_if_paused(poll=0.1):
    """Called between entries in drain_sync_outbox's loop, before each
    entry is processed. Blocks while a foreground bulk-write operation has
    requested exclusive access via pause_worker(), so the drain never
    writes to local_cache at the same time as that operation.

    Always clears _drain_idle_event before returning (marking the drain
    "busy" for the entry it's about to process) and sets it while actually
    waiting out a pause — mirrors _worker_loop's own pause handling below.
    """
    while _drain_pause_event.is_set():
        _drain_idle_event.set()
        time.sleep(poll)
    _drain_idle_event.clear()


def mark_drain_idle():
    """Called once by drain_sync_outbox when its loop is fully done (success
    or error) — marks the drain idle so a later pause_worker() call doesn't
    wait out a drain run that has already finished."""
    _drain_idle_event.set()


def resume_worker():
    """Resume workers previously paused with pause_worker()."""
    _pause_event.clear()
    _drain_pause_event.clear()


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


_drain_started = False


def start_outbox_drain():
    """Recover any SyncOutbox rows left PENDING by a previous crash/restart
    (idempotent, safe to call multiple times).

    enqueue_save()/enqueue_delete() write a durable outbox row before a
    task ever reaches the in-memory queue, but that row only gets cleared
    once the background worker actually pushes it to Neon. If the process
    died in between — a crash, an out-of-memory kill, a deploy restart —
    the row stays PENDING and nothing would otherwise pick it up until
    someone thought to run `manage.py drain_sync_outbox` by hand. Running
    it automatically on every boot closes that gap without changing the
    write-local-first architecture at all — it only affects how quickly a
    row that failed to escape the queue makes it to Neon after restart.
    """
    global _drain_started

    if _drain_started:
        return
    if getattr(settings, 'SYNC_MODE', 'offline') != 'neon_primary':
        return

    _drain_started = True

    def _run():
        time.sleep(5)  # let DB connections + Neon health check settle first
        try:
            from django.core.management import call_command
            call_command('drain_sync_outbox')
        except Exception as exc:
            logger.warning('Startup outbox drain failed (non-fatal): %s', exc)

    threading.Thread(target=_run, daemon=True, name='sync-outbox-drain').start()
    logger.debug('Startup outbox drain scheduled')


def _record_outbox(action: str, table: str, app_label: str,
                    model_name: str, pk: int, row_data: dict | None) -> int | None:
    """Durably record that (table, pk) needs to reach Neon, before the task
    is handed to the in-memory queue. Cheap — a local SQLite insert, not a
    network call. Returns the outbox row's pk, or None on failure (logged,
    never raised — the in-memory queue path must still proceed either way)."""
    try:
        from sync.models import SyncOutbox
        entry = SyncOutbox.objects.using('local_cache').create(
            action=action, db_table=table, app_label=app_label,
            model_name=model_name, row_pk=pk, row_data=row_data,
        )
        return entry.pk
    except Exception as exc:
        logger.warning('Failed to durably record outbox entry (%s %s#%s): %s', action, table, pk, exc)
        return None


def enqueue_save(sender, pk: int, table: str, app_label: str,
                 model_name: str, row_data: dict, origin_client_id: str | None = None):
    """Enqueue a post-commit save task (non-blocking apart from one local
    SQLite insert for durability — see module docstring GUARANTEES).

    origin_client_id identifies the browser tab whose request caused this
    write (see sync/signals.py get_origin_client_id) — carried through to
    the eventual WebSocket broadcast so that tab can skip re-refreshing
    itself over a change it already has (see SyncConsumer.data_changed).
    """
    outbox_id = _record_outbox('upsert', table, app_label, model_name, pk, row_data)
    _task_queue.put({
        'type': 'save',
        'sender': sender,
        'pk': pk,
        'table': table,
        'app_label': app_label,
        'model_name': model_name,
        'row_data': row_data,
        'outbox_id': outbox_id,
        'enqueued_at': time.time(),
        'origin_client_id': origin_client_id,
    })


def enqueue_delete(sender, pk: int, table: str, app_label: str,
                   model_name: str, origin_client_id: str | None = None):
    """Enqueue a post-commit delete task (non-blocking apart from one local
    SQLite insert for durability — see module docstring GUARANTEES)."""
    outbox_id = _record_outbox('delete', table, app_label, model_name, pk, None)
    _task_queue.put({
        'type': 'delete',
        'sender': sender,
        'pk': pk,
        'table': table,
        'app_label': app_label,
        'model_name': model_name,
        'outbox_id': outbox_id,
        'enqueued_at': time.time(),
        'origin_client_id': origin_client_id,
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
        if _pause_event.is_set():
            _idle_event.set()
            time.sleep(0.2)
            continue

        try:
            # Block until a task is available (with timeout for graceful shutdown)
            task = _task_queue.get(timeout=5.0)
        except queue.Empty:
            continue

        _idle_event.clear()
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

            _idle_event.set()


def _process_batch(batch: list):
    """Process a batch of tasks efficiently."""
    from sync.signals import _log_to_neon_changelog, broadcast_data_changed

    # Group by type for efficient processing
    saves = [t for t in batch if t['type'] == 'save']
    deletes = [t for t in batch if t['type'] == 'delete']

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
                broadcast_data_changed(
                    task['table'], 'upsert', [task['row_data']],
                    origin_client_id=task.get('origin_client_id'),
                )

                # 4. Clear the durable outbox record(s) for this row — it
                # reached Neon, so it no longer needs recovery on next boot.
                _clear_outbox(task['table'], task['pk'])

            except Exception as exc:
                logger.debug(
                    'BG push to Neon failed (%s pk=%s): %s — leaving in outbox for retry',
                    task['table'], task['pk'], exc,
                )
                # enqueue_save() already durably recorded this row in
                # SyncOutbox before the task was queued — nothing to do here
                # except make sure that's actually true (defensive fallback
                # for tasks that somehow reached this point without one).
                if task.get('outbox_id') is None:
                    _queue_failed_to_outbox(task, 'upsert', exc)
                # Still broadcast locally so connected clients see the change
                broadcast_data_changed(
                    task['table'], 'upsert', [task['row_data']],
                    origin_client_id=task.get('origin_client_id'),
                )

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
                    origin_client_id=task.get('origin_client_id'),
                )

                # 4. Clear the durable outbox record(s) for this row.
                _clear_outbox(task['table'], task['pk'])

            except Exception as exc:
                logger.debug(
                    'BG delete push to Neon failed (%s pk=%s): %s — leaving in outbox for retry',
                    task['table'], task['pk'], exc,
                )
                if task.get('outbox_id') is None:
                    _queue_failed_to_outbox(task, 'delete', exc)
                broadcast_data_changed(
                    task['table'], 'delete', [{'id': task['pk']}],
                    origin_client_id=task.get('origin_client_id'),
                )



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


def _queue_failed_to_outbox(task, action, exc):
    """Fallback: durably record a task that reached this point without an
    outbox_id (should be rare — enqueue_save/enqueue_delete already record
    one up front). Kept so a failure is never lost even in that case."""
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


def _clear_outbox(table: str, pk: int) -> None:
    """Delete any PENDING SyncOutbox rows for (table, pk) — the row just
    reached Neon successfully, so nothing about it needs recovery anymore.

    Deletes ALL matching rows, not just the one tied to this task's own
    outbox_id: rapid successive writes to the same row before the worker
    gets to them each get their own outbox row at enqueue time, and
    pushing the row's current state to Neon (this task) makes every one
    of those earlier, now-superseded rows moot too.
    """
    try:
        from sync.models import SyncOutbox, SyncOutboxStatus
        SyncOutbox.objects.using('local_cache').filter(
            db_table=table, row_pk=pk, status=SyncOutboxStatus.PENDING,
        ).delete()
    except Exception as exc:
        logger.warning('Failed to clear outbox for %s#%s: %s', table, pk, exc)
