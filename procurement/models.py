from django.db import models
from django.conf import settings
from core.models import TransactionalDocument


class PurchaseOrder(TransactionalDocument):
    """Purchase order header."""
    supplier = models.ForeignKey('partners.Supplier', on_delete=models.PROTECT, related_name='purchase_orders')
    warehouse = models.ForeignKey('warehouses.Warehouse', on_delete=models.PROTECT, related_name='purchase_orders')
    order_date = models.DateField()
    expected_date = models.DateField(null=True, blank=True)
    currency = models.CharField(max_length=10, default='PHP')
    exchange_rate = models.DecimalField(max_digits=12, decimal_places=6, default=1)

    class Meta:
        ordering = ['-created_at']


class PurchaseOrderLine(models.Model):
    """Purchase order line items."""
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name='lines')
    item = models.ForeignKey('catalog.Item', on_delete=models.PROTECT)
    qty_ordered = models.DecimalField(max_digits=15, decimal_places=4)
    qty_received = models.DecimalField(max_digits=15, decimal_places=4, default=0)
    unit = models.ForeignKey('catalog.Unit', on_delete=models.PROTECT)
    unit_price = models.DecimalField(max_digits=15, decimal_places=4, default=0)
    notes = models.TextField(blank=True, default='')

    @property
    def qty_remaining(self):
        return self.qty_ordered - self.qty_received

    @property
    def line_total(self):
        return self.qty_ordered * self.unit_price

    def __str__(self):
        return f"PO Line: {self.item.code} x{self.qty_ordered}"


class GoodsReceipt(TransactionalDocument):
    """Goods Receipt Note (GRN) — receiving document."""
    purchase_order = models.ForeignKey(
        PurchaseOrder, on_delete=models.PROTECT, related_name='goods_receipts',
        null=True, blank=True
    )
    supplier = models.ForeignKey('partners.Supplier', on_delete=models.PROTECT, related_name='goods_receipts')
    warehouse = models.ForeignKey('warehouses.Warehouse', on_delete=models.PROTECT, related_name='goods_receipts')
    receipt_date = models.DateField()

    class Meta:
        ordering = ['-created_at']


class GoodsReceiptLine(models.Model):
    """GRN line items."""
    goods_receipt = models.ForeignKey(GoodsReceipt, on_delete=models.CASCADE, related_name='lines')
    item = models.ForeignKey('catalog.Item', on_delete=models.PROTECT)
    location = models.ForeignKey('warehouses.Location', on_delete=models.PROTECT)
    qty = models.DecimalField(max_digits=15, decimal_places=4)
    unit = models.ForeignKey('catalog.Unit', on_delete=models.PROTECT)
    batch_number = models.CharField(max_length=100, blank=True, default='')
    serial_number = models.CharField(max_length=100, blank=True, default='')
    notes = models.TextField(blank=True, default='')

    def __str__(self):
        return f"GRN Line: {self.item.code} x{self.qty}"


class PurchaseReturn(TransactionalDocument):
    """Return goods to supplier (reverse of GRN)."""
    goods_receipt = models.ForeignKey(
        GoodsReceipt, on_delete=models.PROTECT, related_name='returns',
        null=True, blank=True,
    )
    supplier = models.ForeignKey('partners.Supplier', on_delete=models.PROTECT, related_name='purchase_returns')
    warehouse = models.ForeignKey('warehouses.Warehouse', on_delete=models.PROTECT, related_name='purchase_returns')
    return_date = models.DateField()
    reason = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['-created_at']


class PurchaseReturnLine(models.Model):
    """Purchase return line items."""
    purchase_return = models.ForeignKey(PurchaseReturn, on_delete=models.CASCADE, related_name='lines')
    item = models.ForeignKey('catalog.Item', on_delete=models.PROTECT)
    location = models.ForeignKey('warehouses.Location', on_delete=models.PROTECT)
    qty = models.DecimalField(max_digits=15, decimal_places=4)
    unit = models.ForeignKey('catalog.Unit', on_delete=models.PROTECT)
    reason = models.CharField(max_length=200, blank=True, default='')
    notes = models.TextField(blank=True, default='')

    def __str__(self):
        return f"PR Line: {self.item.code} x{self.qty}"
