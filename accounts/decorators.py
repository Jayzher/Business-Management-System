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
    """Return True if user has the 'Manager (View Only)' role.

    Containment, not exact-match: a restrictive role must cap permissions
    even if an admin also assigns another role on top of it. (Previously
    this checked `roles == {'Manager (View Only)'}`, which meant adding
    any second role silently disabled the restriction entirely.)
    """
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return False
    roles = set(user.user_roles.values_list('role__name', flat=True))
    return 'Manager (View Only)' in roles


def _user_is_viewer(user):
    """Return True if user has the 'Viewer' role (containment — see _user_is_view_only)."""
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return False
    roles = set(user.user_roles.values_list('role__name', flat=True))
    return 'Viewer' in roles


def _user_is_web_version(user):
    """Return True if user has the 'Web Version' role (containment — see _user_is_view_only)."""
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return False
    roles = set(user.user_roles.values_list('role__name', flat=True))
    return 'Web Version' in roles


def _user_is_checker(user):
    """Return True if user has the 'Checker' role (containment — see _user_is_view_only)."""
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return False
    roles = set(user.user_roles.values_list('role__name', flat=True))
    return 'Checker' in roles


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
    Decorator that blocks 'Manager (View Only)', 'Viewer', 'Web Version', and 'Checker' users from
    write operations.  Must be applied AFTER @login_required.
    """
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if _user_is_view_only(request.user) or _user_is_viewer(request.user) or _user_is_web_version(request.user) or _user_is_checker(request.user):
            messages.error(request, 'Your role is view-only. You cannot make changes.')
            if _user_is_viewer(request.user):
                return redirect('item_list')
            referer = request.META.get('HTTP_REFERER', '/dashboard/')
            return redirect(referer)
        return view_func(request, *args, **kwargs)
    return _wrapped


def pos_write_access(view_func):
    """
    Like write_denied_for_viewer, but Viewer is exempted: Viewer has full
    POS-Cashier-equivalent selling rights (open/close shifts, ring up sales,
    manage registers, issue refunds) even though it stays read-only in every
    other module. Still blocks 'Manager (View Only)', 'Web Version', and
    'Checker' from POS writes, same as write_denied_for_viewer.
    """
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if _user_is_view_only(request.user) or _user_is_web_version(request.user) or _user_is_checker(request.user):
            messages.error(request, 'Your role is view-only. You cannot make changes.')
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
    return role_required('Admin', 'Manager', 'Manager (View Only)', 'Web Version', 'Checker')(view_func)


def procurement_access(view_func):
    """Admin, Manager, or Procurement Officer."""
    return role_required('Admin', 'Manager', 'Manager (View Only)', 'Procurement Officer', 'Web Version', 'Checker')(view_func)


def sales_access(view_func):
    """Admin, Manager, or Sales Officer."""
    return role_required('Admin', 'Manager', 'Manager (View Only)', 'Sales Officer', 'Web Version', 'Checker')(view_func)


def warehouse_access(view_func):
    """Admin, Manager, or Warehouse Staff."""
    return role_required('Admin', 'Manager', 'Manager (View Only)', 'Warehouse Staff', 'Web Version', 'Checker')(view_func)


def adjustment_access(view_func):
    """Admin, Manager, or Warehouse Staff - excludes Web Version and Checker."""
    return role_required('Admin', 'Manager', 'Manager (View Only)', 'Warehouse Staff')(view_func)


def pos_access(view_func):
    """Admin, Manager, POS Cashier, Sales Officer, or Viewer - excludes Web Version and Checker.

    Sales Officer is included here to match the sidebar's POS visibility
    (theme.context_processors._ROLE_MAP['POS']) — POS views previously had
    no role decorator at all, so Sales Officer already had access in
    practice; excluding them here would have been a regression, not a fix.

    Viewer is included here with full POS-Cashier-equivalent access (see
    pos_write_access below) even though Viewer is read-only in every other
    module.
    """
    return role_required('Admin', 'Manager', 'Manager (View Only)', 'POS Cashier', 'Sales Officer', 'Viewer')(view_func)


def viewer_access(view_func):
    """Viewer role — catalog read-only access."""
    return role_required('Admin', 'Manager', 'Manager (View Only)', 'Procurement Officer',
                         'Sales Officer', 'Warehouse Staff', 'POS Cashier', 'Viewer', 'Web Version', 'Checker')(view_func)


def services_access(view_func):
    """Admin, Manager, or Sales Officer."""
    return role_required('Admin', 'Manager', 'Manager (View Only)', 'Sales Officer', 'Web Version', 'Checker')(view_func)


def reports_access(view_func):
    """Admin, Manager, Sales Officer, or Procurement Officer."""
    return role_required('Admin', 'Manager', 'Manager (View Only)', 'Sales Officer', 'Procurement Officer', 'Web Version', 'Checker')(view_func)


def cashflow_access(view_func):
    """Admin or Manager only."""
    return role_required('Admin', 'Manager', 'Manager (View Only)', 'Web Version', 'Checker')(view_func)


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


class BlockRestrictedRoleWrites(BasePermission):
    """
    Project-wide default DRF permission: safe methods (GET/HEAD/OPTIONS)
    always pass; unsafe methods (POST/PUT/PATCH/DELETE) are blocked for the
    same restricted roles `write_denied_for_viewer` blocks on the Django
    template-view side (Manager (View Only), Viewer, Web Version, Checker).

    Without this, the REST API bypasses every write restriction enforced
    on the template views, since DRF ViewSets don't go through
    `write_denied_for_viewer` at all.
    """
    def has_permission(self, request, view):
        from rest_framework.permissions import SAFE_METHODS
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if request.method in SAFE_METHODS:
            return True
        if user.is_superuser:
            return True
        return not (
            _user_is_view_only(user) or _user_is_viewer(user)
            or _user_is_web_version(user) or _user_is_checker(user)
        )
