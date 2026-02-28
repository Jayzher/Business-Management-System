from django.contrib import admin
from qr.models import QRCodeTag, ScanEvent


@admin.register(QRCodeTag)
class QRCodeTagAdmin(admin.ModelAdmin):
    list_display = ['qr_uid', 'item', 'location', 'batch_number', 'serial_number', 'is_active', 'printed', 'created_at']
    list_filter = ['is_active', 'printed']
    search_fields = ['item__code', 'item__name', 'batch_number', 'serial_number']
    readonly_fields = ['qr_uid', 'created_at']


@admin.register(ScanEvent)
class ScanEventAdmin(admin.ModelAdmin):
    list_display = ['qr_tag', 'action', 'location', 'qty', 'scanned_by', 'created_at']
    list_filter = ['action']
    readonly_fields = ['created_at']
