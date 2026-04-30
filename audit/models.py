from django.db import models
from django.conf import settings


class AuditLog(models.Model):
    """Generic audit trail for all transactional operations."""
    ACTION_CHOICES = [
        ('CREATE', 'Create'),
        ('UPDATE', 'Update'),
        ('DELETE', 'Delete'),
        ('POST', 'Post'),
        ('APPROVE', 'Approve'),
        ('CANCEL', 'Cancel'),
        ('RESERVE', 'Reserve'),
        ('SCAN', 'Scan'),
    ]
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, related_name='audit_logs'
    )
    action = models.CharField(max_length=20, choices=ACTION_CHOICES, db_index=True)
    model_name = models.CharField(max_length=100, db_index=True)
    object_id = models.PositiveBigIntegerField(null=True, blank=True)
    object_repr = models.CharField(max_length=255, blank=True, default='')
    changes = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f"[{self.action}] {self.model_name}#{self.object_id} by {self.user}"


class ManualLog(models.Model):
    """
    User-entered manual change log for tracking force changes made
    outside the system (e.g. Django Admin, direct DB edits, shell commands).
    """
    ACTION_CHOICES = [
        ('CREATE', 'Created Record'),
        ('UPDATE', 'Updated Record'),
        ('DELETE', 'Deleted Record'),
        ('FIX', 'Data Fix / Correction'),
        ('MIGRATE', 'Data Migration'),
        ('ADMIN', 'Django Admin Change'),
        ('SHELL', 'Shell / Script Change'),
        ('OTHER', 'Other'),
    ]
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, related_name='manual_logs'
    )
    action = models.CharField(max_length=20, choices=ACTION_CHOICES, db_index=True)
    table_name = models.CharField(
        max_length=100, db_index=True,
        help_text='Database table or model name affected (e.g. catalog_item, StockBalance)',
    )
    record_id = models.CharField(
        max_length=100, blank=True, default='',
        help_text='ID or identifier of the affected record(s). Use comma for multiple.',
    )
    fields_changed = models.TextField(
        blank=True, default='',
        help_text='Which fields were changed (e.g. cost_price, qty_on_hand, status)',
    )
    old_value = models.TextField(
        blank=True, default='',
        help_text='Previous value(s) before the change',
    )
    new_value = models.TextField(
        blank=True, default='',
        help_text='New value(s) after the change',
    )
    reason = models.TextField(
        help_text='Why this change was made — be specific',
    )
    notes = models.TextField(
        blank=True, default='',
        help_text='Additional context, ticket numbers, or references',
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.action}] {self.table_name} by {self.user} — {self.reason[:60]}"
