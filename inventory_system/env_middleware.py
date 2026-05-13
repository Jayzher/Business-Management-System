"""
AppEnvironmentMiddleware
========================
Sets the active database context per request.

In Neon-primary mode (SYNC_MODE = 'neon_primary'):
  - Writes go to 'default' (Neon) via the router.
  - Reads go to 'local_cache' (SQLite) via the router.
  - No thread-local switching needed — the router handles it.

In offline mode (SYNC_MODE = 'offline'):
  - Everything goes to 'default' (SQLite).

The middleware ensures any per-request state is clean.
"""

import threading

_thread_local = threading.local()


def get_current_db() -> str:
    """Return the active write DB alias for the current thread."""
    return getattr(_thread_local, 'db', 'default')


def set_current_db(alias: str) -> None:
    """Override the write DB for the current thread (used by test env toggle)."""
    _thread_local.db = alias


class AppEnvironmentMiddleware:
    """Middleware: ensures clean DB state per request."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Default: use 'default' (Neon in primary mode, SQLite in offline)
        _thread_local.db = 'default'
        response = self.get_response(request)
        _thread_local.db = 'default'  # Reset after request
        return response
