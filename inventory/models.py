from django.db import models
from django.conf import settings
from core.models import SoftDeleteModel, TransactionalDocument


class MoveType(models.TextChoices):
    RECEIVE = 'RECEIVE', 'Receive'
    DELIVER = 'DELIVER', 'Deliver'
    TRANSFER = 'TRANSFER', 'Transfer'
    ADJUST = 'ADJUST', 'Adjustment'
    DAMAGE = 'DAMAGE', 'Damage'
    RETURN_IN = 'RETURN_IN', 'Return (In)'
    RETURN_OUT = 'RETURN_OUT', 'Return (Out)'
    POS_SALE = 'POS_SALE', 'POS Sale'


class MoveStatus(models.TextChoices):
    DRAFT = 'DRAFT', 'Draft'
    POSTED = 'POSTED', 'Posted'
    CANCELLED = 'CANCELLED', 'Cancelled'


class StockMove(models.Model):
    """Immutable stock movement ledger — the single source of truth."""
    move_type = models.CharField(max_length=20, choices=MoveType.choices, db_index=True)
    item = models.ForeignKey('catalog.Item', on_delete=models.PROTECT, related_name='stock_moves')
    qty = models.DecimalField(max_digits=15, decimal_places=4)
    unit = models.ForeignKey('catalog.Unit', on_delete=models.PROTECT)
    from_location = models.ForeignKey(
        'warehouses.Location', on_delete=models.PROTECT,
        null=True, blank=True, related_name='moves_out'
    )
    to_location = models.ForeignKey(
        'warehouses.Location', on_delete=models.PROTECT,
        null=True, blank=True, related_name='moves_in'
    )
    reference_type = models.CharField(max_length=50, blank=True, default='')
    reference_id = models.PositiveBigIntegerField(null=True, blank=True)
    reference_number = models.CharField(max_length=50, blank=True, default='')
    status = models.CharField(max_length=20, choices=MoveStatus.choices, default=MoveStatus.DRAFT, db_index=True)
    batch_number = models.CharField(max_length=100, blank=True, default='')
    serial_number = models.CharField(max_length=100, blank=True, default='')
    notes = models.TextField(blank=True, default='')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='stock_moves_created'
    )
    posted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='stock_moves_posted'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    posted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['item', 'posted_at']),
            models.Index(fields=['reference_type', 'reference_id']),
        ]

    def __str__(self):
        return f"{self.move_type} {self.item.code} x{self.qty}"


class StockBalance(models.Model):
    """Denormalized stock balance per item/location for fast lookups."""
    item = models.ForeignKey('catalog.Item', on_delete=models.PROTECT, related_name='balances')
    location = models.ForeignKey('warehouses.Location', on_delete=models.PROTECT, related_name='balances')
    qty_on_hand = models.DecimalField(max_digits=15, decimal_places=4, default=0)
    qty_reserved = models.DecimalField(max_digits=15, decimal_places=4, default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('item', 'location')
        indexes = [
            models.Index(fields=['item', 'location']),
            models.Index(fields=['location', 'item']),
        ]

    def __str__(self):
        return f"{self.item.code} @ {self.location}: {self.qty_on_hand} (reserved: {self.qty_reserved})"

    @property
    def qty_available(self):
        return self.qty_on_hand - self.qty_reserved


class StockReservation(SoftDeleteModel):
    """Reserve stock for sales orders / production."""
    item = models.ForeignKey('catalog.Item', on_delete=models.PROTECT, related_name='reservations')
    location = models.ForeignKey('warehouses.Location', on_delete=models.PROTECT, related_name='reservations')
    qty = models.DecimalField(max_digits=15, decimal_places=4)
    reference_type = models.CharField(max_length=50, blank=True, default='')
    reference_id = models.PositiveBigIntegerField(null=True, blank=True)
    is_fulfilled = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='reservations_created'
    )

    def __str__(self):
        return f"Reserve {self.item.code} x{self.qty} @ {self.location}"


class StockAdjustment(TransactionalDocument):
    """Stock adjustment document (header)."""
    warehouse = models.ForeignKey('warehouses.Warehouse', on_delete=models.PROTECT, related_name='adjustments')
    reason = models.CharField(max_length=200, blank=True, default='')

    class Meta:
        ordering = ['-created_at']


class StockAdjustmentLine(models.Model):
    """Stock adjustment line items."""
    adjustment = models.ForeignKey(StockAdjustment, on_delete=models.CASCADE, related_name='lines')
    item = models.ForeignKey('catalog.Item', on_delete=models.PROTECT)
    location = models.ForeignKey('warehouses.Location', on_delete=models.PROTECT)
    qty_counted = models.DecimalField(max_digits=15, decimal_places=4)
    qty_system = models.DecimalField(max_digits=15, decimal_places=4, default=0)
    unit = models.ForeignKey('catalog.Unit', on_delete=models.PROTECT)
    notes = models.TextField(blank=True, default='')

    @property
    def qty_difference(self):
        return self.qty_counted - self.qty_system

    def __str__(self):
        return f"{self.item.code}: counted={self.qty_counted}, system={self.qty_system}"


class DamagedReport(TransactionalDocument):
    """Damaged stock report (header)."""
    warehouse = models.ForeignKey('warehouses.Warehouse', on_delete=models.PROTECT, related_name='damaged_reports')

    class Meta:
        ordering = ['-created_at']


class DamagedReportLine(models.Model):
    """Damaged stock report line items."""
    report = models.ForeignKey(DamagedReport, on_delete=models.CASCADE, related_name='lines')
    item = models.ForeignKey('catalog.Item', on_delete=models.PROTECT)
    location = models.ForeignKey('warehouses.Location', on_delete=models.PROTECT)
    qty = models.DecimalField(max_digits=15, decimal_places=4)
    unit = models.ForeignKey('catalog.Unit', on_delete=models.PROTECT)
    reason = models.CharField(max_length=200, blank=True, default='')
    photo = models.ImageField(upload_to='damaged/', blank=True, null=True)
    notes = models.TextField(blank=True, default='')

    def __str__(self):
        return f"Damaged: {self.item.code} x{self.qty}"


class StockTransfer(TransactionalDocument):
    """Stock transfer between locations/warehouses."""
    from_warehouse = models.ForeignKey(
        'warehouses.Warehouse', on_delete=models.PROTECT, related_name='transfers_out'
    )
    to_warehouse = models.ForeignKey(
        'warehouses.Warehouse', on_delete=models.PROTECT, related_name='transfers_in'
    )

    class Meta:
        ordering = ['-created_at']


class StockTransferLine(models.Model):
    """Stock transfer line items."""
    transfer = models.ForeignKey(StockTransfer, on_delete=models.CASCADE, related_name='lines')
    item = models.ForeignKey('catalog.Item', on_delete=models.PROTECT)
    from_location = models.ForeignKey(
        'warehouses.Location', on_delete=models.PROTECT, related_name='transfer_lines_out'
    )
    to_location = models.ForeignKey(
        'warehouses.Location', on_delete=models.PROTECT, related_name='transfer_lines_in'
    )
    qty = models.DecimalField(max_digits=15, decimal_places=4)
    unit = models.ForeignKey('catalog.Unit', on_delete=models.PROTECT)
    notes = models.TextField(blank=True, default='')

    def __str__(self):
        return f"Transfer: {self.item.code} x{self.qty}"
