from rest_framework import serializers
from accounts.models import User, Role, UserRole, WarehousePermission


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'phone', 'is_active']
        read_only_fields = ['id']


class RoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Role
        fields = ['id', 'name', 'description']


class UserRoleSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.username', read_only=True)
    role_name = serializers.CharField(source='role.name', read_only=True)

    class Meta:
        model = UserRole
        fields = ['id', 'user', 'user_name', 'role', 'role_name']


class WarehousePermissionSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.username', read_only=True)
    warehouse_name = serializers.CharField(source='warehouse.name', read_only=True)

    class Meta:
        model = WarehousePermission
        fields = [
            'id', 'user', 'user_name', 'warehouse', 'warehouse_name',
            'can_view', 'can_receive', 'can_deliver', 'can_transfer',
            'can_adjust', 'can_manage',
        ]
