import os
from django.apps import AppConfig


class SyncConfig(AppConfig):
    name = 'sync'

    def ready(self):
        import sync.signals  # noqa — registers post_save/post_delete handlers

        # Start background sync worker + startup sync on server boot.
        # Only runs in the main process (not in management commands or migrations).
        # The RUN_MAIN check prevents double-execution in Django's auto-reloader.
        if os.environ.get('RUN_MAIN') == 'true' or not os.environ.get('DJANGO_AUTORELOAD'):
            from sync.background_sync import start_background_worker
            start_background_worker()

            from sync.startup_sync import start_background_sync
            start_background_sync()
