from rest_framework import serializers
from decimal import Decimal
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
    stock_unit_id = serializers.SerializerMethodField()
    stock_unit_name = serializers.SerializerMethodField()
    # Conversion-aware prices
    converted_selling_price = serializers.SerializerMethodField()
    converted_cost_price = serializers.SerializerMethodField()
    conversion_factor = serializers.SerializerMethodField()
    material_spec = MaterialSpecSerializer(read_only=True)
    product_spec = ProductSpecSerializer(read_only=True)

    class Meta:
        model = Item
        fields = [
            'id', 'code', 'name', 'item_type', 'category', 'category_name',
            'default_unit', 'unit_name', 'default_unit_category',
            'selling_unit', 'selling_unit_name',
            'stock_unit_id', 'stock_unit_name',
            'description', 'barcode',
            'cost_price', 'selling_price',
            'converted_selling_price', 'converted_cost_price', 'conversion_factor',
            'minimum_stock', 'maximum_stock', 'reorder_point',
            'image', 'is_active', 'material_spec', 'product_spec',
        ]

    def get_selling_unit_name(self, obj):
        if obj.selling_unit:
            return obj.selling_unit.abbreviation
        return obj.default_unit.abbreviation if obj.default_unit else None

    def get_stock_unit_id(self, obj):
        """Return the item's stock unit ID."""
        return obj.stock_unit.id if obj.stock_unit else None

    def get_stock_unit_name(self, obj):
        """Return the item's stock unit abbreviation."""
        return obj.stock_unit.abbreviation if obj.stock_unit else None

    def get_conversion_factor(self, obj):
        """
        Get conversion factor from stock_unit to the requested selling_unit (if different).
        Request context can include 'unit_id' to specify target unit.
        """
        from catalog.utils import get_conversion_factor
        
        request = self.context.get('request')
        if not request:
            return None
        
        target_unit_id = request.query_params.get('unit') or request.query_params.get('unit_id')
        if not target_unit_id:
            return None
        
        try:
            target_unit = Unit.objects.get(id=int(target_unit_id))
        except (Unit.DoesNotExist, ValueError, TypeError):
            return None
        
        factor = get_conversion_factor(obj.stock_unit, target_unit, item=obj)
        return float(factor) if factor else None

    def get_converted_selling_price(self, obj):
        """
        Get selling price adjusted for the requested unit.
        """
        from catalog.utils import convert_price_for_unit
        
        request = self.context.get('request')
        if not request:
            return float(obj.selling_price)
        
        target_unit_id = request.query_params.get('unit') or request.query_params.get('unit_id')
        if not target_unit_id:
            return float(obj.selling_price)
        
        try:
            target_unit = Unit.objects.get(id=int(target_unit_id))
        except (Unit.DoesNotExist, ValueError, TypeError):
            return float(obj.selling_price)
        
        converted = convert_price_for_unit(
            obj.selling_price,
            obj.stock_unit,
            target_unit,
            item=obj,
            round_places=4
        )
        return float(converted)

    def get_converted_cost_price(self, obj):
        """
        Get cost price adjusted for the requested unit.
        """
        from catalog.utils import convert_price_for_unit
        
        request = self.context.get('request')
        if not request:
            return float(obj.cost_price)
        
        target_unit_id = request.query_params.get('unit') or request.query_params.get('unit_id')
        if not target_unit_id:
            return float(obj.cost_price)
        
        try:
            target_unit = Unit.objects.get(id=int(target_unit_id))
        except (Unit.DoesNotExist, ValueError, TypeError):
            return float(obj.cost_price)
        
        converted = convert_price_for_unit(
            obj.cost_price,
            obj.stock_unit,
            target_unit,
            item=obj,
            round_places=4
        )
        return float(converted)


class ItemListSerializer(serializers.ModelSerializer):
    """Lighter serializer for list views with optional available_qty."""
    category_name = serializers.CharField(source='category.name', read_only=True)
    unit_name = serializers.CharField(source='default_unit.abbreviation', read_only=True)
    default_unit_category = serializers.CharField(source='default_unit.category', read_only=True)
    selling_unit_name = serializers.SerializerMethodField()
    stock_unit_id = serializers.SerializerMethodField()
    stock_unit_name = serializers.SerializerMethodField()
    converted_selling_price = serializers.SerializerMethodField()
    conversion_factor = serializers.SerializerMethodField()
    available_qty = serializers.SerializerMethodField()

    class Meta:
        model = Item
        fields = [
            'id', 'code', 'name', 'item_type', 'category_name',
            'unit_name', 'default_unit_category', 'selling_unit_name',
            'stock_unit_id', 'stock_unit_name',
            'cost_price', 'selling_price', 'converted_selling_price', 'conversion_factor',
            'image', 'is_active', 'available_qty',
        ]

    def get_selling_unit_name(self, obj):
        if obj.selling_unit:
            return obj.selling_unit.abbreviation
        return obj.default_unit.abbreviation if obj.default_unit else None

    def get_stock_unit_id(self, obj):
        """Return the item's stock unit ID."""
        return obj.stock_unit.id if obj.stock_unit else None

    def get_stock_unit_name(self, obj):
        """Return the item's stock unit abbreviation."""
        return obj.stock_unit.abbreviation if obj.stock_unit else None

    def get_conversion_factor(self, obj):
        """Get conversion factor if unit param specified."""
        from catalog.utils import get_conversion_factor
        
        request = self.context.get('request')
        if not request:
            return None
        
        target_unit_id = request.query_params.get('unit') or request.query_params.get('unit_id')
        if not target_unit_id:
            return None
        
        try:
            target_unit = Unit.objects.get(id=int(target_unit_id))
        except (Unit.DoesNotExist, ValueError, TypeError):
            return None
        
        factor = get_conversion_factor(obj.stock_unit, target_unit, item=obj)
        return float(factor) if factor else None

    def get_converted_selling_price(self, obj):
        """Get selling price adjusted for the requested unit."""
        from catalog.utils import convert_price_for_unit
        
        request = self.context.get('request')
        if not request:
            return float(obj.selling_price)
        
        target_unit_id = request.query_params.get('unit') or request.query_params.get('unit_id')
        if not target_unit_id:
            return float(obj.selling_price)
        
        try:
            target_unit = Unit.objects.get(id=int(target_unit_id))
        except (Unit.DoesNotExist, ValueError, TypeError):
            return float(obj.selling_price)
        
        converted = convert_price_for_unit(
            obj.selling_price,
            obj.stock_unit,
            target_unit,
            item=obj,
            round_places=4
        )
        return float(converted)

    def get_available_qty(self, obj):
        available_map = self.context.get('available_map') or {}
        return available_map.get(obj.id)
