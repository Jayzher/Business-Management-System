from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from accounts.models import User, Role, UserRole, WarehousePermission


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ['username', 'email', 'first_name', 'last_name', 'phone', 'is_active', 'is_staff']
    fieldsets = BaseUserAdmin.fieldsets + (
        ('Extra', {'fields': ('phone', 'avatar')}),
    )


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ['name', 'description']


@admin.register(UserRole)
class UserRoleAdmin(admin.ModelAdmin):
    list_display = ['user', 'role']
    list_filter = ['role']


@admin.register(WarehousePermission)
class WarehousePermissionAdmin(admin.ModelAdmin):
    list_display = ['user', 'warehouse', 'can_view', 'can_receive', 'can_deliver', 'can_transfer', 'can_adjust', 'can_manage']
    list_filter = ['warehouse']
