import os
from django.apps import AppConfig


class SyncConfig(AppConfig):
    name = 'sync'

    def ready(self):
        import sync.signals  # noqa — registers post_save handlers

        # Start background sync on server boot (Neon → local_cache).
        # Only runs in the main process (not in management commands or migrations).
        # The RUN_MAIN check prevents double-execution in Django's auto-reloader.
        if os.environ.get('RUN_MAIN') == 'true' or not os.environ.get('DJANGO_AUTORELOAD'):
            from sync.startup_sync import start_background_sync
            start_background_sync()
