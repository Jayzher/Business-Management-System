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
        # so we must check the subcommand itself — the RUN_MAIN/DJANGO_AUTORELOAD
        # check alone doesn't distinguish "runserver" from e.g. "resync_inventory"
        # (both leave DJANGO_AUTORELOAD unset). A one-off command holding a long
        # transaction on local_cache will otherwise race the worker thread for
        # the same SQLite write lock, and the worker will keep pushing whatever
        # that command writes to Neon in the background.
        argv = sys.argv
        subcommand = argv[1] if len(argv) > 1 else None
        is_server_process = (
            subcommand == 'runserver'
            or os.path.basename(argv[0] if argv else '') != 'manage.py'
        )

        if is_server_process and (
            os.environ.get('RUN_MAIN') == 'true' or not os.environ.get('DJANGO_AUTORELOAD')
        ):
            from sync.background_sync import start_background_worker, start_outbox_drain
            start_background_worker()
            start_outbox_drain()

            from sync.startup_sync import start_background_sync
            start_background_sync()
