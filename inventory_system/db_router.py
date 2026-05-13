"""
AppEnvironmentRouter
====================
Routes Django ORM queries to the correct database alias.

Architecture (SYNC_MODE = 'neon_primary'):
  - Writes → 'default' (Neon PostgreSQL, authoritative)
  - Reads  → 'local_cache' (SQLite, fast rendering)

Architecture (SYNC_MODE = 'offline'):
  - Both reads and writes → 'default' (SQLite, same as local_cache)

The signal layer in sync/signals.py mirrors every committed write from
Neon → local_cache synchronously, so reads from local_cache are always
fresh within the same request cycle.

Migration behaviour:
  - ``allow_migrate`` returns ``True`` for ``default``, ``local_cache``,
    ``sqlite``, and ``neon`` aliases.
  - ``test_env`` must be migrated explicitly.
"""

from django.conf import settings

# All app labels whose models should respect the env-routing.
_ROUTED_APP_LABELS = {
    'core', 'accounts', 'catalog', 'partners', 'warehouses',
    'inventory', 'procurement', 'sales', 'qr', 'reports',
    'audit', 'pricing', 'pos', 'services', 'cashflow',
}


def _is_neon_primary():
    """Check if we're running in Neon-primary mode."""
    return getattr(settings, 'SYNC_MODE', 'offline') == 'neon_primary'


class AppEnvironmentRouter:
    """
    Routes reads to local_cache (SQLite) for speed, writes to default (Neon).
    In offline mode, both go to default (which IS SQLite).
    """

    def db_for_read(self, model, **hints):
        if model._meta.app_label in _ROUTED_APP_LABELS:
            if _is_neon_primary():
                # Use local_cache for fast reads.
                # If a hint says 'use_primary' (e.g. right after a write where
                # we need read-your-own-writes consistency), use default.
                if hints.get('instance') and getattr(
                    hints.get('instance'), '_state', None
                ):
                    # After a save, Django may re-read the instance — route to
                    # default so the freshly-written row is visible even before
                    # the mirror fires.
                    instance = hints['instance']
                    if getattr(instance._state, 'db', None) == 'default':
                        return 'default'
                return 'local_cache'
            return 'default'
        return None  # Let Django decide for built-in apps

    def db_for_write(self, model, **hints):
        if model._meta.app_label in _ROUTED_APP_LABELS:
            # Always write to default (Neon in primary mode, SQLite in offline)
            return 'default'
        return None

    def allow_relation(self, obj1, obj2, **hints):
        # Allow relations between objects in any of our managed databases.
        # Both local_cache and default hold the same schema.
        db1 = obj1._state.db or 'default'
        db2 = obj2._state.db or 'default'
        allowed_dbs = {'default', 'local_cache', 'sqlite', 'neon'}
        if db1 in allowed_dbs and db2 in allowed_dbs:
            return True
        return None

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        # Migrations run on these aliases:
        _MIGRATABLE_ALIASES = {'default', 'local_cache', 'sqlite', 'neon'}
        if app_label in _ROUTED_APP_LABELS:
            return db in _MIGRATABLE_ALIASES
        return None  # Let Django decide for built-in apps
