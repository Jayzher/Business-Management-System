from rest_framework import serializers
from pricing.models import PriceList, PriceListItem, DiscountRule


class PriceListItemSerializer(serializers.ModelSerializer):
    item_code = serializers.CharField(source='item.code', read_only=True)
    item_name = serializers.CharField(source='item.name', read_only=True)
    unit_abbr = serializers.CharField(source='unit.abbreviation', read_only=True)

    class Meta:
        model = PriceListItem
        fields = [
            'id', 'price_list', 'item', 'item_code', 'item_name',
            'unit', 'unit_abbr', 'price', 'min_qty',
            'start_date', 'end_date',
        ]


class PriceListSerializer(serializers.ModelSerializer):
    items = PriceListItemSerializer(many=True, read_only=True)
    warehouse_name = serializers.CharField(source='warehouse.name', read_only=True, default='')

    class Meta:
        model = PriceList
        fields = [
            'id', 'name', 'warehouse', 'warehouse_name',
            'currency', 'is_default', 'is_active', 'items',
        ]


class DiscountRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = DiscountRule
        fields = ['id', 'name', 'discount_type', 'value', 'scope', 'is_active']
