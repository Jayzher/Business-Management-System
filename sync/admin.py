from django.contrib import admin
from .models import SyncOutbox


@admin.register(SyncOutbox)
class SyncOutboxAdmin(admin.ModelAdmin):
    list_display = ('id', 'action', 'db_table', 'row_pk', 'status', 'created_at', 'synced_at', 'retry_count')
    list_filter = ('status', 'action', 'db_table')
    search_fields = ('db_table', 'row_pk')
    readonly_fields = ('row_data', 'created_at', 'synced_at')
    ordering = ('-created_at',)

    # Read from local_cache since that's where outbox entries live
    using = 'local_cache'

    def get_queryset(self, request):
        return super().get_queryset(request).using(self.using)

    def save_model(self, request, obj, form, change):
        obj.save(using=self.using)

    def delete_model(self, request, obj):
        obj.delete(using=self.using)
