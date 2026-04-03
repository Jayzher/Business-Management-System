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
    return getattr(_thread_local, 'db', 'default')


def set_current_db(alias: str) -> None:
    _thread_local.db = alias


class AppEnvironmentMiddleware:
    """Middleware: reads session flag and sets thread-local DB alias per request."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Default to production for every request
        _thread_local.db = 'default'

        try:
            # Only allow privileged users to run against test DB
            if (
                hasattr(request, 'session')
                and hasattr(request, 'user')
                and request.user.is_authenticated
                and (request.user.is_superuser or request.user.is_staff)
                and request.session.get('app_env') == 'test'
            ):
                from django.conf import settings  # lazy import
                if 'test_env' in settings.DATABASES:
                    _thread_local.db = 'test_env'

            response = self.get_response(request)
        finally:
            # Always reset — never leak test context to next request on same thread
            _thread_local.db = 'default'

        return response
