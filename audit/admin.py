from django.contrib import admin
from audit.models import AuditLog, ManualLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ['timestamp', 'user', 'action', 'model_name', 'object_id', 'object_repr']
    list_filter = ['action', 'model_name']
    search_fields = ['object_repr', 'model_name']
    readonly_fields = ['timestamp', 'user', 'action', 'model_name', 'object_id', 'object_repr', 'changes', 'ip_address']


@admin.register(ManualLog)
class ManualLogAdmin(admin.ModelAdmin):
    list_display = ['created_at', 'user', 'action', 'table_name', 'record_id', 'reason']
    list_filter = ['action', 'table_name']
    search_fields = ['reason', 'table_name', 'fields_changed', 'notes']
    readonly_fields = ['created_at']
