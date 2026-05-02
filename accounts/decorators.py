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


def _user_is_view_only(user):
    """Return True if user ONLY has the 'Manager (View Only)' role."""
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return False
    roles = set(user.user_roles.values_list('role__name', flat=True))
    return roles == {'Manager (View Only)'}


def _user_is_viewer(user):
    """Return True if user ONLY has the 'Viewer' role."""
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return False
    roles = set(user.user_roles.values_list('role__name', flat=True))
    return roles == {'Viewer'}


def role_required(*role_names):
    """
    Decorator that restricts a view to users who have at least one of the
    specified roles. Superusers always pass.
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            if _user_has_role(request.user, role_names):
                return view_func(request, *args, **kwargs)
            messages.error(request, 'You do not have permission to access this page.')
            # Viewer-only users go to catalog, everyone else to dashboard
            if _user_is_viewer(request.user):
                return redirect('item_list')
            return redirect('dashboard')
        return _wrapped
    return decorator


def write_denied_for_viewer(view_func):
    """
    Decorator that blocks 'Manager (View Only)' and 'Viewer' users from
    write operations.  Must be applied AFTER @login_required.
    """
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if _user_is_view_only(request.user) or _user_is_viewer(request.user):
            messages.error(request, 'Your role is view-only. You cannot make changes.')
            if _user_is_viewer(request.user):
                return redirect('item_list')
            referer = request.META.get('HTTP_REFERER', '/dashboard/')
            return redirect(referer)
        return view_func(request, *args, **kwargs)
    return _wrapped


# ── Convenience shortcuts ─────────────────────────────────────────────────

def admin_required(view_func):
    """Only Admin role (or superuser)."""
    return role_required('Admin')(view_func)


def manager_or_admin_required(view_func):
    """Admin or Manager."""
    return role_required('Admin', 'Manager', 'Manager (View Only)')(view_func)


def procurement_access(view_func):
    """Admin, Manager, or Procurement Officer."""
    return role_required('Admin', 'Manager', 'Manager (View Only)', 'Procurement Officer')(view_func)


def sales_access(view_func):
    """Admin, Manager, or Sales Officer."""
    return role_required('Admin', 'Manager', 'Manager (View Only)', 'Sales Officer')(view_func)


def warehouse_access(view_func):
    """Admin, Manager, or Warehouse Staff."""
    return role_required('Admin', 'Manager', 'Manager (View Only)', 'Warehouse Staff')(view_func)


def pos_access(view_func):
    """Admin, Manager, or POS Cashier."""
    return role_required('Admin', 'Manager', 'Manager (View Only)', 'POS Cashier')(view_func)


def viewer_access(view_func):
    """Viewer role — catalog read-only access."""
    return role_required('Admin', 'Manager', 'Manager (View Only)', 'Procurement Officer',
                         'Sales Officer', 'Warehouse Staff', 'POS Cashier', 'Viewer')(view_func)


def services_access(view_func):
    """Admin, Manager, or Sales Officer."""
    return role_required('Admin', 'Manager', 'Manager (View Only)', 'Sales Officer')(view_func)


def reports_access(view_func):
    """Admin, Manager, Sales Officer, or Procurement Officer."""
    return role_required('Admin', 'Manager', 'Manager (View Only)', 'Sales Officer', 'Procurement Officer')(view_func)


def cashflow_access(view_func):
    """Admin or Manager only."""
    return role_required('Admin', 'Manager', 'Manager (View Only)')(view_func)


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
