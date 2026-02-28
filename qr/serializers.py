from rest_framework import serializers
from qr.models import QRCodeTag, ScanEvent


class QRCodeTagSerializer(serializers.ModelSerializer):
    item_code = serializers.CharField(source='item.code', read_only=True)
    item_name = serializers.CharField(source='item.name', read_only=True)
    location_code = serializers.CharField(source='location.code', read_only=True, default='')

    class Meta:
        model = QRCodeTag
        fields = [
            'id', 'qr_uid', 'item', 'item_code', 'item_name',
            'location', 'location_code', 'batch_number', 'serial_number',
            'is_active', 'printed', 'created_at',
        ]
        read_only_fields = ['id', 'qr_uid', 'created_at']


class ScanEventSerializer(serializers.ModelSerializer):
    qr_uid = serializers.UUIDField(source='qr_tag.qr_uid', read_only=True)
    scanned_by_name = serializers.CharField(source='scanned_by.get_full_name', read_only=True)

    class Meta:
        model = ScanEvent
        fields = [
            'id', 'qr_tag', 'qr_uid', 'action', 'location',
            'qty', 'scanned_by', 'scanned_by_name', 'notes', 'created_at',
        ]
        read_only_fields = ['id', 'created_at']


class QRScanRequestSerializer(serializers.Serializer):
    """Serializer for the scan endpoint request."""
    qr_uid = serializers.UUIDField()
    action = serializers.ChoiceField(choices=['RECEIVE', 'MOVE', 'PICK', 'COUNT', 'INFO'])
    location_id = serializers.IntegerField(required=False)
    qty = serializers.DecimalField(max_digits=15, decimal_places=4, required=False)
    notes = serializers.CharField(required=False, default='')
