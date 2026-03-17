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
        fields = ['id', 'name', 'abbreviation', 'category', 'is_active']


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
    default_unit_category = serializers.CharField(source='default_unit.category', read_only=True)
    selling_unit_name = serializers.SerializerMethodField()
    material_spec = MaterialSpecSerializer(read_only=True)
    product_spec = ProductSpecSerializer(read_only=True)

    class Meta:
        model = Item
        fields = [
            'id', 'code', 'name', 'item_type', 'category', 'category_name',
            'default_unit', 'unit_name', 'default_unit_category',
            'selling_unit', 'selling_unit_name',
            'description', 'barcode',
            'cost_price', 'selling_price',
            'minimum_stock', 'maximum_stock', 'reorder_point',
            'image', 'is_active', 'material_spec', 'product_spec',
        ]

    def get_selling_unit_name(self, obj):
        if obj.selling_unit:
            return obj.selling_unit.abbreviation
        return obj.default_unit.abbreviation if obj.default_unit else None


class ItemListSerializer(serializers.ModelSerializer):
    """Lighter serializer for list views with optional available_qty."""
    category_name = serializers.CharField(source='category.name', read_only=True)
    unit_name = serializers.CharField(source='default_unit.abbreviation', read_only=True)
    default_unit_category = serializers.CharField(source='default_unit.category', read_only=True)
    selling_unit_name = serializers.SerializerMethodField()
    available_qty = serializers.SerializerMethodField()

    class Meta:
        model = Item
        fields = [
            'id', 'code', 'name', 'item_type', 'category_name',
            'unit_name', 'default_unit_category', 'selling_unit_name',
            'cost_price', 'selling_price',
            'image', 'is_active', 'available_qty',
        ]

    def get_selling_unit_name(self, obj):
        if obj.selling_unit:
            return obj.selling_unit.abbreviation
        return obj.default_unit.abbreviation if obj.default_unit else None

    def get_available_qty(self, obj):
        available_map = self.context.get('available_map') or {}
        return available_map.get(obj.id)
