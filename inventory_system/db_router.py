"""
AppEnvironmentRouter
====================
Routes Django ORM queries to the correct database alias.

Architecture (SYNC_MODE = 'neon_primary' — LOCAL-FIRST):
  - Reads  → 'local_cache' (SQLite, instant)
  - Writes → 'local_cache' (SQLite, instant)
  - Background worker pushes writes to 'default' (Neon) asynchronously
  - Neon is the cross-device sync source of truth, but local_cache is
    what the user interacts with for maximum speed.

  Flow:
    1. User action → write lands on local_cache (SQLite) instantly
    2. post_save/post_delete signal fires → enqueues background task
    3. Background worker: pushes to Neon + logs to NeonChangeLog
    4. If Neon is unreachable → queued in SyncOutbox for retry

Architecture (SYNC_MODE = 'offline'):
  - Both reads and writes → 'default' (SQLite, same as local_cache)

Special cases:
  - NeonChangeLog: always reads/writes to 'default' (Neon) directly
  - SyncOutbox: always reads/writes to 'local_cache'

Migration behaviour:
  - ``allow_migrate`` returns ``True`` for ``default``, ``local_cache``,
    ``sqlite``, and ``neon`` aliases.
"""

import logging
import threading
import time

from django.conf import settings
from django.db import connections

logger = logging.getLogger(__name__)

# All app labels whose models should respect the env-routing.
_ROUTED_APP_LABELS = {
    'core', 'accounts', 'catalog', 'partners', 'warehouses',
    'inventory', 'procurement', 'sales', 'qr', 'reports',
    'audit', 'pricing', 'pos', 'services', 'cashflow',
}

# ── Neon health tracking ───────────────────────────────────────────────
_neon_health_lock = threading.Lock()
_neon_healthy = True
_neon_last_check = 0.0
_HEALTH_CHECK_INTERVAL = 10.0
_HEALTH_CHECK_INTERVAL_HEALTHY = 60.0


def _check_neon_health() -> bool:
    """Quick connectivity check to Neon. Returns True if reachable."""
    global _neon_healthy, _neon_last_check

    now = time.time()
    interval = _HEALTH_CHECK_INTERVAL_HEALTHY if _neon_healthy else _HEALTH_CHECK_INTERVAL

    if (now - _neon_last_check) < interval:
        return _neon_healthy

    with _neon_health_lock:
        if (time.time() - _neon_last_check) < interval:
            return _neon_healthy

        try:
            conn = connections['default']
            conn.ensure_connection()
            _neon_healthy = True
        except Exception as exc:
            if _neon_healthy:
                logger.warning('Neon unreachable: %s', exc)
            _neon_healthy = False

        _neon_last_check = time.time()

    return _neon_healthy


def is_neon_healthy() -> bool:
    """Public API: check if Neon is currently reachable."""
    if not _is_neon_primary():
        return True
    return _check_neon_health()


def force_neon_recheck() -> bool:
    """Force an immediate health check."""
    global _neon_last_check
    _neon_last_check = 0.0
    return _check_neon_health()


def _is_neon_primary():
    """Check if we're running in Neon-primary mode."""
    return getattr(settings, 'SYNC_MODE', 'offline') == 'neon_primary'


class AppEnvironmentRouter:
    """
    LOCAL-FIRST router:
      - ALL reads → local_cache (SQLite, instant)
      - ALL writes → local_cache (SQLite, instant)
      - Background worker handles Neon sync

    This means the user NEVER waits for Neon. Every create, update, delete
    is instant because it only touches the local SQLite file.
    """

    def db_for_read(self, model, **hints):
        # NeonChangeLog always reads from Neon (it's the cross-device log)
        if model._meta.app_label == 'sync' and model._meta.model_name == 'neonchangelog':
            return 'default'

        if model._meta.app_label in _ROUTED_APP_LABELS:
            if _is_neon_primary():
                return 'local_cache'
            return 'default'
        return None

    def db_for_write(self, model, **hints):
        # NeonChangeLog always writes to Neon directly
        if model._meta.app_label == 'sync' and model._meta.model_name == 'neonchangelog':
            return 'default'

        if model._meta.app_label in _ROUTED_APP_LABELS:
            if _is_neon_primary():
                # ALL writes go to local_cache — background worker syncs to Neon
                return 'local_cache'
            return 'default'
        return None

    def allow_relation(self, obj1, obj2, **hints):
        db1 = obj1._state.db or 'default'
        db2 = obj2._state.db or 'default'
        allowed_dbs = {'default', 'local_cache', 'sqlite', 'neon'}
        if db1 in allowed_dbs and db2 in allowed_dbs:
            return True
        return None

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        _MIGRATABLE_ALIASES = {'default', 'local_cache', 'sqlite', 'neon'}
        if app_label in _ROUTED_APP_LABELS:
            return db in _MIGRATABLE_ALIASES
        if app_label == 'sync':
            return db in _MIGRATABLE_ALIASES
        return None
