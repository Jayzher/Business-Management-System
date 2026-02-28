from rest_framework import serializers
from inventory.models import (
    StockMove, StockBalance, StockReservation,
    StockAdjustment, StockAdjustmentLine,
    DamagedReport, DamagedReportLine,
    StockTransfer, StockTransferLine,
)


class StockMoveSerializer(serializers.ModelSerializer):
    item_code = serializers.CharField(source='item.code', read_only=True)
    item_name = serializers.CharField(source='item.name', read_only=True)
    unit_abbr = serializers.CharField(source='unit.abbreviation', read_only=True)
    from_location_code = serializers.CharField(source='from_location.code', read_only=True, default='')
    to_location_code = serializers.CharField(source='to_location.code', read_only=True, default='')
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True)

    class Meta:
        model = StockMove
        fields = [
            'id', 'move_type', 'item', 'item_code', 'item_name',
            'qty', 'unit', 'unit_abbr',
            'from_location', 'from_location_code', 'to_location', 'to_location_code',
            'reference_type', 'reference_id', 'reference_number',
            'status', 'batch_number', 'serial_number', 'notes',
            'created_by', 'created_by_name', 'posted_by', 'created_at', 'posted_at',
        ]
        read_only_fields = ['id', 'created_at', 'posted_at']


class StockBalanceSerializer(serializers.ModelSerializer):
    item_code = serializers.CharField(source='item.code', read_only=True)
    item_name = serializers.CharField(source='item.name', read_only=True)
    location_code = serializers.CharField(source='location.code', read_only=True)
    warehouse_code = serializers.CharField(source='location.warehouse.code', read_only=True)
    qty_available = serializers.DecimalField(max_digits=15, decimal_places=4, read_only=True)

    class Meta:
        model = StockBalance
        fields = [
            'id', 'item', 'item_code', 'item_name',
            'location', 'location_code', 'warehouse_code',
            'qty_on_hand', 'qty_reserved', 'qty_available', 'updated_at',
        ]


class StockAdjustmentLineSerializer(serializers.ModelSerializer):
    item_code = serializers.CharField(source='item.code', read_only=True)
    qty_difference = serializers.DecimalField(max_digits=15, decimal_places=4, read_only=True)

    class Meta:
        model = StockAdjustmentLine
        fields = [
            'id', 'item', 'item_code', 'location', 'qty_counted',
            'qty_system', 'qty_difference', 'unit', 'notes',
        ]


class StockAdjustmentSerializer(serializers.ModelSerializer):
    lines = StockAdjustmentLineSerializer(many=True, read_only=True)
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True)

    class Meta:
        model = StockAdjustment
        fields = [
            'id', 'document_number', 'status', 'warehouse', 'reason',
            'notes', 'created_by', 'created_by_name',
            'approved_by', 'approved_at', 'posted_by', 'posted_at',
            'created_at', 'lines',
        ]
        read_only_fields = ['id', 'document_number', 'created_at']


class DamagedReportLineSerializer(serializers.ModelSerializer):
    item_code = serializers.CharField(source='item.code', read_only=True)

    class Meta:
        model = DamagedReportLine
        fields = [
            'id', 'item', 'item_code', 'location', 'qty', 'unit',
            'reason', 'photo', 'notes',
        ]


class DamagedReportSerializer(serializers.ModelSerializer):
    lines = DamagedReportLineSerializer(many=True, read_only=True)
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True)

    class Meta:
        model = DamagedReport
        fields = [
            'id', 'document_number', 'status', 'warehouse', 'notes',
            'created_by', 'created_by_name',
            'approved_by', 'approved_at', 'posted_by', 'posted_at',
            'created_at', 'lines',
        ]
        read_only_fields = ['id', 'document_number', 'created_at']


class StockTransferLineSerializer(serializers.ModelSerializer):
    item_code = serializers.CharField(source='item.code', read_only=True)

    class Meta:
        model = StockTransferLine
        fields = [
            'id', 'item', 'item_code', 'from_location', 'to_location',
            'qty', 'unit', 'notes',
        ]


class StockTransferSerializer(serializers.ModelSerializer):
    lines = StockTransferLineSerializer(many=True, read_only=True)
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True)

    class Meta:
        model = StockTransfer
        fields = [
            'id', 'document_number', 'status',
            'from_warehouse', 'to_warehouse', 'notes',
            'created_by', 'created_by_name',
            'approved_by', 'approved_at', 'posted_by', 'posted_at',
            'created_at', 'lines',
        ]
        read_only_fields = ['id', 'document_number', 'created_at']
