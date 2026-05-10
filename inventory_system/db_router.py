"""
AppEnvironmentRouter
====================
Routes Django ORM queries to the correct database alias (``default`` for
production, ``test_env`` for test) based on the thread-local value set by
``AppEnvironmentMiddleware``.

Migration behaviour:
  - ``allow_migrate`` returns ``True`` for ``default``, ``sqlite`` and
    ``neon`` aliases. ``sqlite``/``neon`` are used by the ``db_sync``
    management command to migrate those destinations before copying data.
  - All other aliases (e.g. ``test_env``) must be migrated explicitly
    with ``manage.py migrate --database=<alias>``.
"""

from .env_middleware import get_current_db

# All app labels whose models should respect the env-routing.
# Django's built-in apps (auth, admin, contenttypes, sessions, …) always
# use 'default' because they are excluded from this set.
_ROUTED_APP_LABELS = {
    'core', 'accounts', 'catalog', 'partners', 'warehouses',
    'inventory', 'procurement', 'sales', 'qr', 'reports',
    'audit', 'pricing', 'pos', 'services', 'cashflow',
}


class AppEnvironmentRouter:
    """Routes reads and writes for project apps to the active environment DB."""

    def db_for_read(self, model, **hints):
        if model._meta.app_label in _ROUTED_APP_LABELS:
            db = get_current_db()
            from django.conf import settings
            return db if db in settings.DATABASES else 'default'
        return None  # Let Django decide for built-in apps

    def db_for_write(self, model, **hints):
        if model._meta.app_label in _ROUTED_APP_LABELS:
            db = get_current_db()
            from django.conf import settings
            return db if db in settings.DATABASES else 'default'
        return None

    def allow_relation(self, obj1, obj2, **hints):
        # Allow cross-model relations (same DB guaranteed by router logic above)
        return True

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        # Migrations run on:
        #   - 'default'   : primary environment DB
        #   - 'sqlite'    : explicit local SQLite alias used by db_sync
        #   - 'neon'      : explicit Neon PostgreSQL alias used by db_sync
        # Other aliases (e.g. 'test_env') must be migrated explicitly with
        # manage.py migrate --database=<alias>.
        _MIGRATABLE_ALIASES = {'default', 'sqlite', 'neon'}
        if app_label in _ROUTED_APP_LABELS:
            return db in _MIGRATABLE_ALIASES
        return None  # Let Django decide for built-in apps
