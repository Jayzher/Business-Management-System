"""
AppEnvironmentRouter
====================
Routes Django ORM queries to the correct database alias.

Architecture (SYNC_MODE = 'neon_primary'):
  - Writes → 'default' (Neon PostgreSQL, authoritative)
  - Reads  → 'local_cache' (SQLite, fast rendering)
  - Fallback: if Neon is unreachable, writes go to 'local_cache' and
    are queued in SyncOutbox for later replay.

Architecture (SYNC_MODE = 'offline'):
  - Both reads and writes → 'default' (SQLite, same as local_cache)

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
# We cache the Neon health status for a short period to avoid hammering
# the connection on every single ORM call.

_neon_health_lock = threading.Lock()
_neon_healthy = True
_neon_last_check = 0.0
_HEALTH_CHECK_INTERVAL = 10.0  # seconds between re-checks when unhealthy
_HEALTH_CHECK_INTERVAL_HEALTHY = 60.0  # seconds between checks when healthy


def _check_neon_health() -> bool:
    """
    Quick connectivity check to Neon.  Returns True if reachable.
    Caches the result to avoid per-query overhead.
    """
    global _neon_healthy, _neon_last_check

    now = time.time()
    interval = _HEALTH_CHECK_INTERVAL_HEALTHY if _neon_healthy else _HEALTH_CHECK_INTERVAL

    if (now - _neon_last_check) < interval:
        return _neon_healthy

    with _neon_health_lock:
        # Double-check after acquiring lock
        if (time.time() - _neon_last_check) < interval:
            return _neon_healthy

        try:
            conn = connections['default']
            conn.ensure_connection()
            _neon_healthy = True
        except Exception as exc:
            if _neon_healthy:
                # Transition from healthy → unhealthy
                logger.warning('Neon unreachable, activating fallback mode: %s', exc)
            _neon_healthy = False

        _neon_last_check = time.time()

    return _neon_healthy


def is_neon_healthy() -> bool:
    """Public API: check if Neon is currently reachable."""
    if not _is_neon_primary():
        return True  # In offline mode, "Neon" is local — always healthy
    return _check_neon_health()


def force_neon_recheck() -> bool:
    """Force an immediate health check (used after drain_outbox succeeds)."""
    global _neon_last_check
    _neon_last_check = 0.0
    return _check_neon_health()


def _is_neon_primary():
    """Check if we're running in Neon-primary mode."""
    return getattr(settings, 'SYNC_MODE', 'offline') == 'neon_primary'


class AppEnvironmentRouter:
    """
    Routes reads to local_cache (SQLite) for speed, writes to default (Neon).
    Falls back to local_cache for writes when Neon is unreachable.
    """

    def db_for_read(self, model, **hints):
        if model._meta.app_label in _ROUTED_APP_LABELS:
            if _is_neon_primary():
                # After a save, Django may re-read the instance — route to
                # the DB it was written to for read-your-own-writes.
                if hints.get('instance') and getattr(
                    hints.get('instance'), '_state', None
                ):
                    instance = hints['instance']
                    if getattr(instance._state, 'db', None) == 'default':
                        return 'default'
                return 'local_cache'
            return 'default'
        return None

    def db_for_write(self, model, **hints):
        if model._meta.app_label in _ROUTED_APP_LABELS:
            if _is_neon_primary():
                # Check Neon health — fall back to local_cache if unreachable
                if _check_neon_health():
                    return 'default'
                else:
                    # Activate fallback mode so signals know to queue to outbox
                    from sync.signals import set_fallback_active
                    set_fallback_active(True)
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
        # sync app (SyncOutbox) should migrate on local_cache too
        if app_label == 'sync':
            return db in _MIGRATABLE_ALIASES
        return None
