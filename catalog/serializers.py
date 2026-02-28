from rest_framework import serializers
from catalog.models import Category, Unit, UnitConversion, Item, MaterialSpec, ProductSpec


class CategorySerializer(serializers.ModelSerializer):
    parent_name = serializers.CharField(source='parent.name', read_only=True, default='')

    class Meta:
        model = Category
        fields = ['id', 'code', 'name', 'parent', 'parent_name', 'description', 'is_active']


class UnitSerializer(serializers.ModelSerializer):
    class Meta:
        model = Unit
        fields = ['id', 'name', 'abbreviation', 'is_active']


class UnitConversionSerializer(serializers.ModelSerializer):
    from_unit_name = serializers.CharField(source='from_unit.abbreviation', read_only=True)
    to_unit_name = serializers.CharField(source='to_unit.abbreviation', read_only=True)

    class Meta:
        model = UnitConversion
        fields = ['id', 'from_unit', 'from_unit_name', 'to_unit', 'to_unit_name', 'factor']


class MaterialSpecSerializer(serializers.ModelSerializer):
    class Meta:
        model = MaterialSpec
        fields = ['id', 'thickness', 'length', 'width', 'color', 'alloy', 'grade']


class ProductSpecSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductSpec
        fields = ['id', 'model_name', 'variant', 'dimensions', 'weight']


class ItemSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True)
    unit_name = serializers.CharField(source='default_unit.abbreviation', read_only=True)
    material_spec = MaterialSpecSerializer(read_only=True)
    product_spec = ProductSpecSerializer(read_only=True)

    class Meta:
        model = Item
        fields = [
            'id', 'code', 'name', 'item_type', 'category', 'category_name',
            'default_unit', 'unit_name', 'description', 'barcode',
            'cost_price', 'selling_price',
            'minimum_stock', 'maximum_stock', 'reorder_point',
            'image', 'is_active', 'material_spec', 'product_spec',
        ]


class ItemListSerializer(serializers.ModelSerializer):
    """Lighter serializer for list views."""
    category_name = serializers.CharField(source='category.name', read_only=True)
    unit_name = serializers.CharField(source='default_unit.abbreviation', read_only=True)

    class Meta:
        model = Item
        fields = [
            'id', 'code', 'name', 'item_type', 'category_name',
            'unit_name', 'cost_price', 'selling_price', 'image', 'is_active',
        ]
