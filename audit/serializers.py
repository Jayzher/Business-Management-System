from rest_framework import serializers
from audit.models import AuditLog, ManualLog


class AuditLogSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', default='System')

    class Meta:
        model = AuditLog
        fields = [
            'id', 'username', 'action', 'model_name', 'object_id',
            'object_repr', 'changes', 'ip_address', 'timestamp',
        ]


class ManualLogSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', default=None, read_only=True)
    action_display = serializers.CharField(source='get_action_display', read_only=True)

    class Meta:
        model = ManualLog
        fields = [
            'id', 'username', 'action', 'action_display', 'table_name',
            'record_id', 'fields_changed', 'old_value', 'new_value',
            'reason', 'notes', 'created_at',
        ]
        read_only_fields = ['id', 'username', 'created_at']


class ManualLogCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ManualLog
        fields = [
            'action', 'table_name', 'record_id', 'fields_changed',
            'old_value', 'new_value', 'reason', 'notes',
        ]
