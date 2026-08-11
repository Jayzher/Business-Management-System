import os
import sys
from django.apps import AppConfig


class SyncConfig(AppConfig):
    name = 'sync'

    def ready(self):
        import sync.signals  # noqa — registers post_save/post_delete handlers

        # Start background sync worker + startup sync on server boot.
        # Only runs in the main process (not in management commands or migrations).
        # AppConfig.ready() fires for every `manage.py <subcommand>` invocation,
        # so we must check the subcommand itself — RUN_MAIN alone doesn't
        # distinguish "runserver" from e.g. "resync_inventory" (both leave
        # RUN_MAIN unset outside the autoreloader). A one-off command holding a
        # long transaction on local_cache will otherwise race the worker thread
        # for the same SQLite write lock, and the worker will keep pushing
        # whatever that command writes to Neon in the background.
        argv = sys.argv
        subcommand = argv[1] if len(argv) > 1 else None
        is_server_process = (
            subcommand == 'runserver'
            or os.path.basename(argv[0] if argv else '') != 'manage.py'
        )

        # `runserver` (without --noreload) re-execs itself as a child process
        # with RUN_MAIN=true once the StatReloader is set up; ready() fires in
        # BOTH the initial watcher process and that child. Only the child
        # actually serves requests, so when autoreload is in play we must wait
        # for RUN_MAIN=='true' — otherwise the watcher process starts its own
        # background worker + outbox drain too, and two OS processes end up
        # hammering db.sqlite3 concurrently (this is what was causing
        # "database is locked" errors). When autoreload is NOT in play
        # (--noreload, or a non-runserver entrypoint like daphne/gunicorn in
        # production), RUN_MAIN is never set at all and this is the only
        # process, so we must proceed without waiting for it.
        autoreload_active = subcommand == 'runserver' and '--noreload' not in argv

        if is_server_process and (
            os.environ.get('RUN_MAIN') == 'true' or not autoreload_active
        ):
            from sync.background_sync import start_background_worker, start_outbox_drain
            start_background_worker()
            start_outbox_drain()

            from sync.startup_sync import start_background_sync
            start_background_sync()
