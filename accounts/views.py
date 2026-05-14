from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Count, Prefetch
from django.http import HttpResponseForbidden
from django.views.decorators.http import require_POST
from rest_framework import viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.models import User, Role, UserRole, WarehousePermission
from accounts.forms import (
    UserCreateForm, UserEditForm, PasswordResetForm, RoleForm,
)
from accounts.serializers import (
    UserSerializer, RoleSerializer, UserRoleSerializer, WarehousePermissionSerializer,
)
from accounts.decorators import admin_required


# ── API Views ──────────────────────────────────────────────────────────────

class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    search_fields = ['username', 'first_name', 'last_name', 'email']


class RoleViewSet(viewsets.ModelViewSet):
    queryset = Role.objects.all()
    serializer_class = RoleSerializer


class UserRoleViewSet(viewsets.ModelViewSet):
    queryset = UserRole.objects.select_related('user', 'role').all()
    serializer_class = UserRoleSerializer


class WarehousePermissionViewSet(viewsets.ModelViewSet):
    queryset = WarehousePermission.objects.select_related('user', 'warehouse').all()
    serializer_class = WarehousePermissionSerializer


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def me(request):
    serializer = UserSerializer(request.user)
    return Response(serializer.data)


# ── Login / Logout Template Views ──────────────────────────────────────────

def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            # Redirect Viewer-only users to catalog instead of dashboard
            from accounts.decorators import _user_is_viewer
            if _user_is_viewer(user):
                return redirect('item_list')
            next_url = request.GET.get('next', '/dashboard/')
            return redirect(next_url)
        else:
            messages.error(request, 'Invalid username or password.')
    return render(request, 'accounts/login.html')


@require_POST
def logout_view(request):
    logout(request)
    return redirect('login')


# ═══════════════════════════════════════════════════════════════════════════
# SUPERADMIN: USER MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════════

@login_required
@admin_required
def user_list(request):
    """List all users with their assigned roles."""
    q = (request.GET.get('q') or '').strip()
    role_filter = (request.GET.get('role') or '').strip()

    users = User.objects.prefetch_related(
        Prefetch('user_roles', queryset=UserRole.objects.select_related('role'))
    ).order_by('username')

    if q:
        users = users.filter(
            username__icontains=q
        ) | users.filter(
            first_name__icontains=q
        ) | users.filter(
            last_name__icontains=q
        ) | users.filter(
            email__icontains=q
        )
        users = users.distinct()

    if role_filter:
        users = users.filter(user_roles__role__name=role_filter).distinct()

    roles = Role.objects.order_by('name')

    return render(request, 'accounts/user_list.html', {
        'users': users,
        'roles': roles,
        'q': q,
        'role_filter': role_filter,
    })


@login_required
@admin_required
def user_create(request):
    if request.method == 'POST':
        form = UserCreateForm(request.POST, acting_user=request.user)
        if form.is_valid():
            user = form.save()
            messages.success(request, f'User "{user.username}" created.')
            return redirect('user_list')
    else:
        form = UserCreateForm(acting_user=request.user)
    return render(request, 'accounts/user_form.html', {
        'form': form,
        'title': 'New User',
        'mode': 'create',
    })


@login_required
@admin_required
def user_edit(request, pk):
    target = get_object_or_404(User, pk=pk)
    # Non-superusers cannot edit superusers
    if target.is_superuser and not request.user.is_superuser:
        messages.error(request, 'Only superusers can edit another superuser.')
        return redirect('user_list')

    if request.method == 'POST':
        form = UserEditForm(request.POST, instance=target, acting_user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, f'User "{target.username}" updated.')
            return redirect('user_list')
    else:
        form = UserEditForm(instance=target, acting_user=request.user)

    return render(request, 'accounts/user_form.html', {
        'form': form,
        'title': f'Edit: {target.username}',
        'target_user': target,
        'mode': 'edit',
    })


@login_required
@admin_required
def user_password_reset(request, pk):
    target = get_object_or_404(User, pk=pk)
    if target.is_superuser and not request.user.is_superuser:
        messages.error(request, 'Only superusers can reset another superuser\'s password.')
        return redirect('user_list')

    if request.method == 'POST':
        form = PasswordResetForm(request.POST)
        if form.is_valid():
            target.set_password(form.cleaned_data['password1'])
            target.save(update_fields=['password'])
            if target.pk == request.user.pk:
                # Keep current session valid after changing own password
                update_session_auth_hash(request, target)
            messages.success(request, f'Password reset for "{target.username}".')
            return redirect('user_list')
    else:
        form = PasswordResetForm()

    return render(request, 'accounts/user_password_reset.html', {
        'form': form,
        'target_user': target,
    })


@login_required
@admin_required
def user_toggle_active(request, pk):
    """Activate/deactivate a user. POST only."""
    if request.method != 'POST':
        return redirect('user_list')
    target = get_object_or_404(User, pk=pk)
    if target.pk == request.user.pk:
        messages.error(request, 'You cannot deactivate your own account.')
        return redirect('user_list')
    if target.is_superuser and not request.user.is_superuser:
        messages.error(request, 'Only superusers can deactivate a superuser.')
        return redirect('user_list')
    target.is_active = not target.is_active
    target.save(update_fields=['is_active'])
    state = 'activated' if target.is_active else 'deactivated'
    messages.success(request, f'User "{target.username}" {state}.')
    return redirect('user_list')


@login_required
@admin_required
def user_delete(request, pk):
    target = get_object_or_404(User, pk=pk)
    if target.pk == request.user.pk:
        messages.error(request, 'You cannot delete your own account.')
        return redirect('user_list')
    if target.is_superuser and not request.user.is_superuser:
        messages.error(request, 'Only superusers can delete a superuser.')
        return redirect('user_list')

    if request.method == 'POST':
        username = target.username
        target.delete()
        messages.success(request, f'User "{username}" deleted.')
        return redirect('user_list')
    return render(request, 'accounts/user_confirm_delete.html', {
        'target_user': target,
    })


# ═══════════════════════════════════════════════════════════════════════════
# SUPERADMIN: ROLE MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════════

# Display-only map of what each built-in role can access.
ROLE_MODULES = {
    'Admin': 'All modules + Settings',
    'Manager': 'All modules (no Settings)',
    'Manager (View Only)': 'All modules, NO write actions',
    'Procurement Officer': 'Dashboard, Catalog, Partners, Warehouses, Procurement, Inventory, Reports',
    'Sales Officer': 'Dashboard, Catalog, Partners, Sales, Services, Pricing, POS, Reports',
    'Warehouse Staff': 'Dashboard, Catalog, Warehouses, Inventory, Supplies, QR Codes',
    'POS Cashier': 'Dashboard, Catalog, POS',
    'Viewer': 'Catalog only (read-only)',
}


@login_required
@admin_required
def role_list(request):
    roles = Role.objects.annotate(user_count=Count('role_users')).order_by('name')
    # Attach display modules for each
    role_rows = []
    for r in roles:
        role_rows.append({
            'obj': r,
            'user_count': r.user_count,
            'modules': ROLE_MODULES.get(r.name, '—'),
        })
    return render(request, 'accounts/role_list.html', {
        'role_rows': role_rows,
    })


@login_required
@admin_required
def role_create(request):
    if request.method == 'POST':
        form = RoleForm(request.POST)
        if form.is_valid():
            role = form.save()
            messages.success(request, f'Role "{role.name}" created.')
            return redirect('role_list')
    else:
        form = RoleForm()
    return render(request, 'accounts/role_form.html', {
        'form': form,
        'title': 'New Role',
    })


@login_required
@admin_required
def role_edit(request, pk):
    role = get_object_or_404(Role, pk=pk)
    if request.method == 'POST':
        form = RoleForm(request.POST, instance=role)
        if form.is_valid():
            form.save()
            messages.success(request, f'Role "{role.name}" updated.')
            return redirect('role_list')
    else:
        form = RoleForm(instance=role)
    return render(request, 'accounts/role_form.html', {
        'form': form,
        'title': f'Edit Role: {role.name}',
        'role': role,
    })


@login_required
@admin_required
def role_delete(request, pk):
    role = get_object_or_404(Role, pk=pk)
    # Protect built-in roles from accidental deletion
    built_in = set(ROLE_MODULES.keys())
    if role.name in built_in:
        messages.error(request, f'"{role.name}" is a built-in role and cannot be deleted.')
        return redirect('role_list')

    if request.method == 'POST':
        name = role.name
        role.delete()
        messages.success(request, f'Role "{name}" deleted.')
        return redirect('role_list')
    return render(request, 'accounts/role_confirm_delete.html', {
        'role': role,
    })
