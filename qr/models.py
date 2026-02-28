import uuid
from django.db import models
from django.conf import settings
from core.models import TimeStampedModel


class QRCodeTag(TimeStampedModel):
    """QR code tag linked to an item, optionally to a location/batch/serial."""
    qr_uid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, db_index=True)
    item = models.ForeignKey('catalog.Item', on_delete=models.PROTECT, related_name='qr_tags')
    location = models.ForeignKey(
        'warehouses.Location', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='qr_tags'
    )
    batch_number = models.CharField(max_length=100, blank=True, default='')
    serial_number = models.CharField(max_length=100, blank=True, default='')
    is_active = models.BooleanField(default=True, db_index=True)
    image = models.ImageField(upload_to='qrcodes/', blank=True, null=True)
    printed = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"QR:{self.qr_uid} -> {self.item.code}"


class ScanAction(models.TextChoices):
    RECEIVE = 'RECEIVE', 'Receive'
    MOVE = 'MOVE', 'Move'
    PICK = 'PICK', 'Pick'
    COUNT = 'COUNT', 'Count'
    INFO = 'INFO', 'Info'


class ScanEvent(TimeStampedModel):
    """Log of every QR scan."""
    qr_tag = models.ForeignKey(QRCodeTag, on_delete=models.PROTECT, related_name='scan_events')
    action = models.CharField(max_length=20, choices=ScanAction.choices)
    location = models.ForeignKey(
        'warehouses.Location', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='scan_events'
    )
    qty = models.DecimalField(max_digits=15, decimal_places=4, null=True, blank=True)
    scanned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='scan_events'
    )
    notes = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Scan: {self.qr_tag.qr_uid} [{self.action}] by {self.scanned_by}"
