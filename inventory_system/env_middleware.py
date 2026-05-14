"""
AppEnvironmentMiddleware
========================
Ensures clean DB state per request and resets fallback mode.

In Neon-primary mode:
  - Writes go to 'default' (Neon) via the router.
  - If Neon is unreachable, the router falls back to 'local_cache'.
  - The fallback flag is reset after each request so it doesn't leak.
"""

import threading

_thread_local = threading.local()


def get_current_db() -> str:
    """Return the active write DB alias for the current thread."""
    return getattr(_thread_local, 'db', 'default')


def set_current_db(alias: str) -> None:
    """Override the write DB for the current thread."""
    _thread_local.db = alias


class AppEnvironmentMiddleware:
    """Middleware: ensures clean DB state and resets fallback per request."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        _thread_local.db = 'default'

        # Reset fallback flag at the start of each request
        from sync.signals import set_fallback_active
        set_fallback_active(False)

        response = self.get_response(request)

        # Reset after request to prevent leaking into the next one
        set_fallback_active(False)
        _thread_local.db = 'default'

        return response
