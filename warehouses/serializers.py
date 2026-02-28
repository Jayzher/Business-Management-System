from rest_framework import serializers
from warehouses.models import Warehouse, Location


class WarehouseSerializer(serializers.ModelSerializer):
    manager_name = serializers.CharField(source='manager.get_full_name', read_only=True, default='')
    location_count = serializers.SerializerMethodField()

    class Meta:
        model = Warehouse
        fields = [
            'id', 'code', 'name', 'address', 'city', 'phone',
            'manager', 'manager_name', 'allow_negative_stock',
            'is_active', 'location_count',
        ]

    def get_location_count(self, obj):
        return obj.locations.count()


class LocationSerializer(serializers.ModelSerializer):
    warehouse_name = serializers.CharField(source='warehouse.name', read_only=True)
    parent_code = serializers.CharField(source='parent.code', read_only=True, default='')
    full_path = serializers.CharField(read_only=True)

    class Meta:
        model = Location
        fields = [
            'id', 'warehouse', 'warehouse_name', 'code', 'name',
            'parent', 'parent_code', 'location_type', 'is_pickable',
            'is_active', 'full_path',
        ]
