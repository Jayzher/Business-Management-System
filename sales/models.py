from django.db import models
from django.conf import settings
from core.models import TransactionalDocument, SalesChannel


class SalesOrderLineDiscountType(models.TextChoices):
    PERCENT = 'PERCENT', 'Percentage (%)'
    AMOUNT  = 'AMOUNT',  'Fixed Amount'


class FulfillmentType(models.TextChoices):
    DELIVER = 'DELIVER', 'Delivery'
    PICKUP = 'PICKUP', 'Pickup'


class PaymentStatus(models.TextChoices):
    UNPAID = 'UNPAID', 'Unpaid'
    PARTIAL = 'PARTIAL', 'Partially Paid'
    PAID = 'PAID', 'Paid'


class SalesOrder(TransactionalDocument):
    """Sales order header."""
    customer = models.ForeignKey('partners.Customer', on_delete=models.PROTECT, related_name='sales_orders')
    warehouse = models.ForeignKey('warehouses.Warehouse', on_delete=models.PROTECT, related_name='sales_orders')
    order_date = models.DateField()
    delivery_date = models.DateField(null=True, blank=True)
    fulfillment_type = models.CharField(
        max_length=10, choices=FulfillmentType.choices,
        default=FulfillmentType.DELIVER,
        help_text='How the customer will receive the goods.',
    )
    shipping_address = models.TextField(blank=True, default='')
    currency = models.CharField(max_length=10, default='PHP')
    exchange_rate = models.DecimalField(max_digits=12, decimal_places=6, default=1)
    payment_status = models.CharField(
        max_length=20, choices=PaymentStatus.choices,
        default=PaymentStatus.UNPAID, db_index=True,
    )
    sales_channel = models.ForeignKey(
        SalesChannel, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='sales_orders',
    )
    receipt_no = models.CharField(max_length=100, blank=True, default='')

    class Meta:
        ordering = ['-created_at']


class SalesOrderLine(models.Model):
    """Sales order line items."""
    sales_order = models.ForeignKey(SalesOrder, on_delete=models.CASCADE, related_name='lines')
    item = models.ForeignKey('catalog.Item', on_delete=models.PROTECT)
    qty_ordered = models.DecimalField(max_digits=15, decimal_places=4)
    qty_delivered = models.DecimalField(max_digits=15, decimal_places=4, default=0)
    qty_reserved = models.DecimalField(max_digits=15, decimal_places=4, default=0)
    unit = models.ForeignKey('catalog.Unit', on_delete=models.PROTECT)
    unit_price = models.DecimalField(max_digits=15, decimal_places=4, default=0)
    discount_type = models.CharField(
        max_length=10,
        choices=SalesOrderLineDiscountType.choices,
        default=SalesOrderLineDiscountType.PERCENT,
    )
    discount_value = models.DecimalField(
        max_digits=15, decimal_places=4, default=0,
        help_text='Discount amount or percentage depending on discount_type',
    )
    batch_number = models.CharField(max_length=100, blank=True, default='')
    serial_number = models.CharField(max_length=100, blank=True, default='')
    notes = models.TextField(blank=True, default='')

    @property
    def qty_remaining(self):
        return self.qty_ordered - self.qty_delivered

    @property
    def discount_amount(self):
        from decimal import Decimal
        if self.discount_type == SalesOrderLineDiscountType.AMOUNT:
            return self.discount_value
        subtotal = self.qty_ordered * self.unit_price
        return subtotal * (self.discount_value / Decimal('100'))

    @property
    def line_total(self):
        return self.qty_ordered * self.unit_price - self.discount_amount

    def __str__(self):
        return f"SO Line: {self.item.code} x{self.qty_ordered}"


class SalesOrderPriceListLine(models.Model):
    """
    A PriceList (bundle/package) applied to a Sales Order.
    Each PriceListItem inside becomes an effective line at the PriceList price
    (overriding the catalog item selling_price).
    """
    sales_order = models.ForeignKey(
        SalesOrder, on_delete=models.CASCADE, related_name='price_list_lines',
    )
    price_list = models.ForeignKey(
        'pricing.PriceList', on_delete=models.PROTECT, related_name='so_lines',
    )
    qty_multiplier = models.DecimalField(
        max_digits=15, decimal_places=4, default=1,
        help_text='Multiply every PriceListItem qty by this factor (usually 1).',
    )
    discount_type = models.CharField(
        max_length=10,
        choices=SalesOrderLineDiscountType.choices,
        default=SalesOrderLineDiscountType.PERCENT,
    )
    discount_value = models.DecimalField(
        max_digits=15, decimal_places=4, default=0,
        help_text='Bundle-level discount applied on top of individual item prices.',
    )
    notes = models.TextField(blank=True, default='')

    @property
    def bundle_subtotal(self):
        from decimal import Decimal
        total = Decimal('0')
        for pli in self.price_list.items.select_related('item', 'unit').all():
            total += pli.price * self.qty_multiplier
        return total

    @property
    def bundle_discount_amount(self):
        from decimal import Decimal
        sub = self.bundle_subtotal
        if self.discount_type == SalesOrderLineDiscountType.AMOUNT:
            return self.discount_value
        return sub * (self.discount_value / Decimal('100'))

    @property
    def bundle_total(self):
        return self.bundle_subtotal - self.bundle_discount_amount

    def __str__(self):
        return f"Bundle: {self.price_list.name} x{self.qty_multiplier}"


class DeliveryNote(TransactionalDocument):
    """Delivery / shipment document."""
    sales_order = models.ForeignKey(
        SalesOrder, on_delete=models.PROTECT, related_name='deliveries',
        null=True, blank=True
    )
    customer = models.ForeignKey('partners.Customer', on_delete=models.PROTECT, related_name='deliveries')
    warehouse = models.ForeignKey('warehouses.Warehouse', on_delete=models.PROTECT, related_name='deliveries')
    delivery_date = models.DateField()
    shipping_address = models.TextField(blank=True, default='')
    driver_name = models.CharField(max_length=100, blank=True, default='')
    vehicle_number = models.CharField(max_length=50, blank=True, default='')

    class Meta:
        ordering = ['-created_at']


class DeliveryLine(models.Model):
    """Delivery line items."""
    delivery = models.ForeignKey(DeliveryNote, on_delete=models.CASCADE, related_name='lines')
    item = models.ForeignKey('catalog.Item', on_delete=models.PROTECT)
    location = models.ForeignKey('warehouses.Location', on_delete=models.PROTECT)
    qty = models.DecimalField(max_digits=15, decimal_places=4)
    unit = models.ForeignKey('catalog.Unit', on_delete=models.PROTECT)
    batch_number = models.CharField(max_length=100, blank=True, default='')
    serial_number = models.CharField(max_length=100, blank=True, default='')
    notes = models.TextField(blank=True, default='')

    def __str__(self):
        return f"Delivery Line: {self.item.code} x{self.qty}"


class SalesReturn(TransactionalDocument):
    """Return goods from customer (reverse of Delivery)."""
    sales_order = models.ForeignKey(
        SalesOrder, on_delete=models.PROTECT, related_name='returns',
        null=True, blank=True,
    )
    delivery_note = models.ForeignKey(
        DeliveryNote, on_delete=models.PROTECT, related_name='returns',
        null=True, blank=True,
    )
    customer = models.ForeignKey('partners.Customer', on_delete=models.PROTECT, related_name='sales_returns')
    warehouse = models.ForeignKey('warehouses.Warehouse', on_delete=models.PROTECT, related_name='sales_returns')
    return_date = models.DateField()
    reason = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['-created_at']


class SalesReturnLine(models.Model):
    """Sales return line items."""
    sales_return = models.ForeignKey(SalesReturn, on_delete=models.CASCADE, related_name='lines')
    item = models.ForeignKey('catalog.Item', on_delete=models.PROTECT)
    location = models.ForeignKey('warehouses.Location', on_delete=models.PROTECT)
    qty = models.DecimalField(max_digits=15, decimal_places=4)
    unit = models.ForeignKey('catalog.Unit', on_delete=models.PROTECT)
    reason = models.CharField(max_length=200, blank=True, default='')
    notes = models.TextField(blank=True, default='')

    def __str__(self):
        return f"SR Line: {self.item.code} x{self.qty}"
