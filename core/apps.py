import logging
import os
import threading

from django.apps import AppConfig

logger = logging.getLogger(__name__)


def _run_neon_sync():
    """Execute a full neon_to_local db_sync pass (optional fallback timer)."""
    try:
        from django.core.management import call_command
        call_command('db_sync', direction='neon_to_local', verbosity=1)
        logger.info('Background Neon\u2192SQLite sync completed.')
    except Exception as exc:
        logger.error('Background Neon\u2192SQLite sync failed: %s', exc)


def _schedule_sync(interval):
    _run_neon_sync()
    timer = threading.Timer(interval, _schedule_sync, args=(interval,))
    timer.daemon = True
    timer.start()


class CoreConfig(AppConfig):
    name = 'core'

    def ready(self):
        # Only start in the Django main process — skip autoreload child process.
        if os.environ.get('RUN_MAIN') != 'true':
            return

        from django.conf import settings
        db_engine = settings.DATABASES.get('default', {}).get('ENGINE', '')
        is_sqlite = 'sqlite3' in db_engine

        if not (is_sqlite and hasattr(settings, 'NEON_URL')):
            return

        # One-shot sync on server start (default: enabled).
        if getattr(settings, 'NEON_INITIAL_SYNC', True):
            logger.info('NEON_INITIAL_SYNC=True — running startup Neon\u2192SQLite sync.')
            t = threading.Thread(target=_run_neon_sync, daemon=True, name='neon-initial-sync')
            t.start()

        # Optional periodic fallback timer.
        interval = getattr(settings, 'NEON_SYNC_INTERVAL', 9999999)
        if interval > 0:
            logger.info('Scheduling fallback Neon\u2192SQLite sync every %ds.', interval)
            timer = threading.Timer(interval, _schedule_sync, args=(interval,))
            timer.daemon = True
            timer.start()
