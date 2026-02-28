from rest_framework import serializers
from procurement.models import PurchaseOrder, PurchaseOrderLine, GoodsReceipt, GoodsReceiptLine


class PurchaseOrderLineSerializer(serializers.ModelSerializer):
    item_code = serializers.CharField(source='item.code', read_only=True)
    item_name = serializers.CharField(source='item.name', read_only=True)
    unit_abbr = serializers.CharField(source='unit.abbreviation', read_only=True)
    qty_remaining = serializers.DecimalField(max_digits=15, decimal_places=4, read_only=True)
    line_total = serializers.DecimalField(max_digits=15, decimal_places=4, read_only=True)

    class Meta:
        model = PurchaseOrderLine
        fields = [
            'id', 'item', 'item_code', 'item_name',
            'qty_ordered', 'qty_received', 'qty_remaining',
            'unit', 'unit_abbr', 'unit_price', 'line_total', 'notes',
        ]


class PurchaseOrderSerializer(serializers.ModelSerializer):
    lines = PurchaseOrderLineSerializer(many=True, read_only=True)
    supplier_name = serializers.CharField(source='supplier.name', read_only=True)
    warehouse_name = serializers.CharField(source='warehouse.name', read_only=True)
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True)

    class Meta:
        model = PurchaseOrder
        fields = [
            'id', 'document_number', 'status',
            'supplier', 'supplier_name', 'warehouse', 'warehouse_name',
            'order_date', 'expected_date', 'notes',
            'created_by', 'created_by_name',
            'approved_by', 'approved_at', 'posted_by', 'posted_at',
            'created_at', 'lines',
        ]
        read_only_fields = ['id', 'document_number', 'created_at']


class GoodsReceiptLineSerializer(serializers.ModelSerializer):
    item_code = serializers.CharField(source='item.code', read_only=True)
    item_name = serializers.CharField(source='item.name', read_only=True)
    unit_abbr = serializers.CharField(source='unit.abbreviation', read_only=True)

    class Meta:
        model = GoodsReceiptLine
        fields = [
            'id', 'item', 'item_code', 'item_name',
            'location', 'qty', 'unit', 'unit_abbr',
            'batch_number', 'serial_number', 'notes',
        ]


class GoodsReceiptSerializer(serializers.ModelSerializer):
    lines = GoodsReceiptLineSerializer(many=True, read_only=True)
    supplier_name = serializers.CharField(source='supplier.name', read_only=True)
    warehouse_name = serializers.CharField(source='warehouse.name', read_only=True)
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True)

    class Meta:
        model = GoodsReceipt
        fields = [
            'id', 'document_number', 'status',
            'purchase_order', 'supplier', 'supplier_name',
            'warehouse', 'warehouse_name', 'receipt_date', 'notes',
            'created_by', 'created_by_name',
            'approved_by', 'approved_at', 'posted_by', 'posted_at',
            'created_at', 'lines',
        ]
        read_only_fields = ['id', 'document_number', 'created_at']
