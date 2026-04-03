"""
AppEnvironmentRouter
====================
Routes Django ORM queries to the correct database alias (``default`` for
production, ``test_env`` for test) based on the thread-local value set by
``AppEnvironmentMiddleware``.

Migration behaviour:
  - ``allow_migrate`` returns ``True`` only for the ``default`` alias.
    This prevents accidental schema migrations against the test database.
    Run test DB migrations explicitly when needed.
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
        # Migrations should only run on the production ('default') database.
        # Run test DB migrations explicitly: manage.py migrate --database=test_env
        if app_label in _ROUTED_APP_LABELS:
            return db == 'default'
        return None  # Let Django decide for built-in apps
