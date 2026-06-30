"""
NeonFallbackBackend — desktop-mode authentication backend.

Flow:
  1. Try local SQLite first (fast, works offline).
  2. If the user isn't found locally, attempt Neon PostgreSQL.
  3. On Neon success: cache the user + their roles in local SQLite,
     then return the local copy so the session is bound to SQLite.

After the first successful login the user record exists locally, so
all subsequent logins are instant and work without an internet connection.
"""

import logging

from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model

logger = logging.getLogger(__name__)

User = get_user_model()

_NEON_ALIAS = '_desktop_neon_auth'


def _add_neon_connection():
    """Temporarily register a Neon DB alias. Returns True on success."""
    from django.conf import settings
    import dj_database_url

    neon_url = getattr(settings, 'NEON_URL', None)
    if not neon_url:
        return False
    try:
        settings.DATABASES[_NEON_ALIAS] = dj_database_url.parse(
            neon_url,
            conn_max_age=0,
            ssl_require=True,
        )
        return True
    except Exception as exc:
        logger.warning('NeonFallback: failed to parse NEON_URL: %s', exc)
        return False


def _remove_neon_connection():
    """Close and unregister the temporary Neon alias."""
    from django.conf import settings
    from django.db import connections

    try:
        connections[_NEON_ALIAS].close()
    except Exception:
        pass

    # Remove from Django's thread-local connection cache
    try:
        if hasattr(connections._connections, _NEON_ALIAS):
            delattr(connections._connections, _NEON_ALIAS)
    except Exception:
        pass

    settings.DATABASES.pop(_NEON_ALIAS, None)


def _sync_user_from_neon(neon_user):
    """
    Write the Neon user (and their roles) into the local SQLite database.
    Returns the local User instance.
    """
    from accounts.models import Role, UserRole

    local_user, _ = User.objects.using('default').update_or_create(
        pk=neon_user.pk,
        defaults={
            'username': neon_user.username,
            'email': neon_user.email,
            'password': neon_user.password,
            'first_name': neon_user.first_name,
            'last_name': neon_user.last_name,
            'is_staff': neon_user.is_staff,
            'is_active': neon_user.is_active,
            'is_superuser': neon_user.is_superuser,
            'date_joined': neon_user.date_joined,
            'phone': neon_user.phone,
        },
    )

    # Sync roles so permission checks work offline after first login
    try:
        neon_roles = (
            UserRole.objects
            .using(_NEON_ALIAS)
            .filter(user_id=neon_user.pk)
            .select_related('role')
        )
        for ur in neon_roles:
            role, _ = Role.objects.using('default').update_or_create(
                pk=ur.role.pk,
                defaults={'name': ur.role.name, 'description': ur.role.description},
            )
            UserRole.objects.using('default').get_or_create(
                user=local_user,
                role=role,
            )
    except Exception as exc:
        logger.warning('NeonFallback: could not sync roles for %s: %s', neon_user.username, exc)

    return local_user


class NeonFallbackBackend(ModelBackend):
    """
    Desktop auth backend: local SQLite first, Neon as fallback.
    Registered via AUTHENTICATION_BACKENDS in settings_desktop.py.
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        # ── Fast path: local SQLite ──────────────────────────────────────────
        local_user = super().authenticate(
            request, username=username, password=password, **kwargs
        )
        if local_user is not None:
            return local_user

        # ── Slow path: Neon fallback ─────────────────────────────────────────
        if not username or not password:
            return None

        if not _add_neon_connection():
            return None

        try:
            from django.db import connections
            connections[_NEON_ALIAS].ensure_connection()
        except Exception as exc:
            logger.warning('NeonFallback: Neon unreachable — %s', exc)
            _remove_neon_connection()
            return None

        try:
            neon_user = (
                User.objects
                .using(_NEON_ALIAS)
                .filter(username=username, is_active=True)
                .first()
            )
            if neon_user is None or not neon_user.check_password(password):
                return None

            local_user = _sync_user_from_neon(neon_user)
            logger.info(
                'NeonFallback: synced user "%s" from Neon and logged in.', username
            )
            return local_user

        except Exception as exc:
            logger.error('NeonFallback: unexpected error — %s', exc)
            return None

        finally:
            _remove_neon_connection()
