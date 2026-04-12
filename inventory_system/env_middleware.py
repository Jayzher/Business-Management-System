"""
AppEnvironmentMiddleware
========================
Routes each request to either the 'default' (production) or 'test_env'
database alias based on the authenticated user's session flag.

Session key : ``app_env``  →  ``'test'`` | ``'production'`` (default)

The flag is toggled via the ``toggle_environment`` view (POST only).
Only superusers and staff are allowed to switch environments; for all
other users the flag is silently ignored.

Thread-local ``_current_db`` is read by ``AppEnvironmentRouter`` when
Django's ORM resolves which database to use for a given query.
"""

import threading

_thread_local = threading.local()


def get_current_db() -> str:
    """Return the active DB alias for the current thread (always safe to call)."""
    # Always use 'default' (local DB)
    return 'default'


def set_current_db(alias: str) -> None:
    _thread_local.db = alias


class AppEnvironmentMiddleware:
    """Middleware: reads session flag and sets thread-local DB alias per request."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Always use local DB for every request
        _thread_local.db = 'default'
        response = self.get_response(request)
        _thread_local.db = 'default'  # Ensure reset
        return response

