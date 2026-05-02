from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.html import format_html
from accounts.models import User, Role, UserRole, WarehousePermission


# ── Role → module access map (for display only) ──────────────────────────
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


class UserRoleInline(admin.TabularInline):
    model = UserRole
    extra = 1
    autocomplete_fields = ['role']


class WarehousePermissionInline(admin.TabularInline):
    model = WarehousePermission
    extra = 0
    autocomplete_fields = ['warehouse']


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ['username', 'email', 'first_name', 'last_name', 'phone', 'get_roles', 'is_active', 'is_staff']
    fieldsets = BaseUserAdmin.fieldsets + (
        ('Extra', {'fields': ('phone', 'avatar')}),
    )
    inlines = [UserRoleInline, WarehousePermissionInline]

    @admin.display(description='Roles')
    def get_roles(self, obj):
        roles = obj.user_roles.select_related('role').all()
        if not roles:
            return '-'
        return ', '.join(r.role.name for r in roles)


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ['name', 'description', 'get_modules', 'get_user_count']
    search_fields = ['name']
    readonly_fields = ['get_modules']

    @admin.display(description='Accessible Modules')
    def get_modules(self, obj):
        modules = ROLE_MODULES.get(obj.name, '')
        if modules:
            return format_html('<span style="color:#666;font-size:.85em;">{}</span>', modules)
        return '-'

    @admin.display(description='Users')
    def get_user_count(self, obj):
        return obj.role_users.count()


@admin.register(UserRole)
class UserRoleAdmin(admin.ModelAdmin):
    list_display = ['user', 'role', 'get_modules']
    list_filter = ['role']
    autocomplete_fields = ['user', 'role']

    @admin.display(description='Accessible Modules')
    def get_modules(self, obj):
        return ROLE_MODULES.get(obj.role.name, '-')


@admin.register(WarehousePermission)
class WarehousePermissionAdmin(admin.ModelAdmin):
    list_display = ['user', 'warehouse', 'can_view', 'can_receive', 'can_deliver', 'can_transfer', 'can_adjust', 'can_manage']
    list_filter = ['warehouse']
    autocomplete_fields = ['user', 'warehouse']
