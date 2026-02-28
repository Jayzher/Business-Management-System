from rest_framework import serializers
from sales.models import SalesOrder, SalesOrderLine, DeliveryNote, DeliveryLine


class SalesOrderLineSerializer(serializers.ModelSerializer):
    item_code = serializers.CharField(source='item.code', read_only=True)
    item_name = serializers.CharField(source='item.name', read_only=True)
    unit_abbr = serializers.CharField(source='unit.abbreviation', read_only=True)
    qty_remaining = serializers.DecimalField(max_digits=15, decimal_places=4, read_only=True)
    line_total = serializers.DecimalField(max_digits=15, decimal_places=4, read_only=True)

    class Meta:
        model = SalesOrderLine
        fields = [
            'id', 'item', 'item_code', 'item_name',
            'qty_ordered', 'qty_delivered', 'qty_reserved', 'qty_remaining',
            'unit', 'unit_abbr', 'unit_price', 'line_total', 'notes',
        ]


class SalesOrderSerializer(serializers.ModelSerializer):
    lines = SalesOrderLineSerializer(many=True, read_only=True)
    customer_name = serializers.CharField(source='customer.name', read_only=True)
    warehouse_name = serializers.CharField(source='warehouse.name', read_only=True)
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True)

    class Meta:
        model = SalesOrder
        fields = [
            'id', 'document_number', 'status',
            'customer', 'customer_name', 'warehouse', 'warehouse_name',
            'order_date', 'delivery_date', 'shipping_address', 'notes',
            'created_by', 'created_by_name',
            'approved_by', 'approved_at', 'posted_by', 'posted_at',
            'created_at', 'lines',
        ]
        read_only_fields = ['id', 'document_number', 'created_at']


class DeliveryLineSerializer(serializers.ModelSerializer):
    item_code = serializers.CharField(source='item.code', read_only=True)
    item_name = serializers.CharField(source='item.name', read_only=True)
    unit_abbr = serializers.CharField(source='unit.abbreviation', read_only=True)

    class Meta:
        model = DeliveryLine
        fields = [
            'id', 'item', 'item_code', 'item_name',
            'location', 'qty', 'unit', 'unit_abbr', 'notes',
        ]


class DeliveryNoteSerializer(serializers.ModelSerializer):
    lines = DeliveryLineSerializer(many=True, read_only=True)
    customer_name = serializers.CharField(source='customer.name', read_only=True)
    warehouse_name = serializers.CharField(source='warehouse.name', read_only=True)
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True)

    class Meta:
        model = DeliveryNote
        fields = [
            'id', 'document_number', 'status',
            'sales_order', 'customer', 'customer_name',
            'warehouse', 'warehouse_name', 'delivery_date',
            'shipping_address', 'driver_name', 'vehicle_number', 'notes',
            'created_by', 'created_by_name',
            'approved_by', 'approved_at', 'posted_by', 'posted_at',
            'created_at', 'lines',
        ]
        read_only_fields = ['id', 'document_number', 'created_at']
