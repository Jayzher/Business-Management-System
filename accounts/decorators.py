"""
Role-based access control decorators for WIS.
Uses the accounts.Role / accounts.UserRole models.
"""
from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages


def _user_has_role(user, role_names):
    """Check if user has any of the given role names (case-insensitive)."""
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    lower_names = [r.lower() for r in role_names]
    return user.user_roles.filter(role__name__iregex=r'^(' + '|'.join(lower_names) + r')$').exists()


def role_required(*role_names):
    """
    Decorator that restricts a view to users who have at least one of the
    specified roles. Superusers always pass.

    Usage:
        @login_required
        @role_required('Admin', 'Manager', 'Procurement Officer')
        def my_view(request):
            ...
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            if _user_has_role(request.user, role_names):
                return view_func(request, *args, **kwargs)
            messages.error(request, 'You do not have permission to access this page.')
            return redirect('dashboard')
        return _wrapped
    return decorator


# ── Convenience shortcuts ─────────────────────────────────────────────────

def admin_required(view_func):
    """Only Admin role (or superuser)."""
    return role_required('Admin')(view_func)


def manager_or_admin_required(view_func):
    """Admin or Manager."""
    return role_required('Admin', 'Manager')(view_func)


def procurement_access(view_func):
    """Admin, Manager, or Procurement Officer."""
    return role_required('Admin', 'Manager', 'Procurement Officer')(view_func)


def sales_access(view_func):
    """Admin, Manager, or Sales Officer."""
    return role_required('Admin', 'Manager', 'Sales Officer')(view_func)


def warehouse_access(view_func):
    """Admin, Manager, or Warehouse Staff."""
    return role_required('Admin', 'Manager', 'Warehouse Staff')(view_func)


def pos_access(view_func):
    """Admin, Manager, or POS Cashier."""
    return role_required('Admin', 'Manager', 'POS Cashier')(view_func)


# ── DRF Permission class ─────────────────────────────────────────────────

from rest_framework.permissions import BasePermission


class HasRole(BasePermission):
    """
    DRF permission that checks the user's WIS roles.
    Set `required_roles` on the viewset or pass via kwargs.

    Usage on ViewSet:
        permission_classes = [IsAuthenticated, HasRole]
        required_roles = ['Admin', 'Manager']
    """
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.is_superuser:
            return True
        required = getattr(view, 'required_roles', [])
        if not required:
            return True
        return _user_has_role(request.user, required)
