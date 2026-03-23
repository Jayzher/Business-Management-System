"""
Catalog utilities for unit conversions and price calculations.
Flexible logic for handling unit conversion factors across all selling scenarios.
"""
from decimal import Decimal
from typing import Optional, Union
from django.db.models import QuerySet


def get_conversion_factor(from_unit, to_unit, item=None) -> Optional[Decimal]:
    """
    Get the conversion factor between two units.
    
    Args:
        from_unit: Source unit object
        to_unit: Target unit object
        item: Optional item for item-specific conversions
        
    Returns:
        Decimal conversion factor or None if not found
        
    Example:
        From 1 roll to meters: factor = 50 (1 roll = 50 meters)
    """
    if not from_unit or not to_unit:
        return None
        
    if from_unit.pk == to_unit.pk:
        return Decimal('1')
    
    from catalog.models import UnitConversion
    
    # Try item-specific conversion first
    if item:
        direct = UnitConversion.objects.filter(
            from_unit=from_unit,
            to_unit=to_unit,
            item=item,
            is_active=True
        ).first()
        if direct:
            return direct.factor
    
    # Try global conversion
    direct = UnitConversion.objects.filter(
        from_unit=from_unit,
        to_unit=to_unit,
        item__isnull=True,
        is_active=True
    ).first()
    if direct:
        return direct.factor
    
    # Try reverse conversion
    if item:
        reverse = UnitConversion.objects.filter(
            from_unit=to_unit,
            to_unit=from_unit,
            item=item,
            is_active=True
        ).first()
        if reverse and reverse.factor != 0:
            return Decimal('1') / reverse.factor
    
    reverse = UnitConversion.objects.filter(
        from_unit=to_unit,
        to_unit=from_unit,
        item__isnull=True,
        is_active=True
    ).first()
    if reverse and reverse.factor != 0:
        return Decimal('1') / reverse.factor
    
    return None


def convert_price_for_unit(
    base_price: Union[Decimal, float, str],
    base_unit,
    selling_unit,
    item=None,
    round_places: int = 4
) -> Decimal:
    """
    Convert a price from one unit to another based on conversion factors.
    
    The logic: if the selling_unit is different from base_unit, adjust the price
    proportionally using the conversion factor.
    
    Example:
        base_price = 100 (per Piece)
        base_unit = Piece
        selling_unit = Foot
        1 Piece = 19.7 Feet
        
        Result: 100 / 19.7 ≈ 5.08 (price per Foot)
        
    Args:
        base_price: The base price in the base_unit
        base_unit: The unit the base_price is denominated in
        selling_unit: The unit we want to price in
        item: Optional item for item-specific conversions
        round_places: Decimal places to round result to
        
    Returns:
        Decimal price adjusted for the selling_unit
    """
    if not base_unit or not selling_unit:
        return Decimal(str(base_price)).quantize(Decimal(10) ** -round_places)
    
    # If same unit, return as-is
    if base_unit.pk == selling_unit.pk:
        return Decimal(str(base_price)).quantize(Decimal(10) ** -round_places)
    
    base_price_dec = Decimal(str(base_price))
    
    # Get conversion factor from base_unit to selling_unit
    # If 1 base_unit = X selling_units, then
    # price_in_selling_unit = base_price / X
    factor = get_conversion_factor(base_unit, selling_unit, item)
    
    if factor is None:
        # No conversion configured, return base price
        return base_price_dec.quantize(Decimal(10) ** -round_places)
    
    if factor == 0:
        # Invalid factor
        return base_price_dec.quantize(Decimal(10) ** -round_places)
    
    # Adjust price: divide by factor because if 1 unit = X selling_units,
    # then the price per selling_unit is base_price / X
    adjusted_price = base_price_dec / factor
    
    return adjusted_price.quantize(Decimal(10) ** -round_places)


def get_item_price_for_unit(item, selling_unit, use_selling_price: bool = True) -> Decimal:
    """
    Get the item's price adjusted for a specific selling unit.
    
    Args:
        item: Item object
        selling_unit: Unit to price in
        use_selling_price: If True, use selling_price; if False, use cost_price
        
    Returns:
        Decimal price in the specified unit
    """
    if not item or not selling_unit:
        return Decimal('0')
    
    price = item.selling_price if use_selling_price else item.cost_price
    
    # Get the base unit for this item (stock_unit or default_unit)
    base_unit = item.stock_unit  # This already handles selling_unit fallback
    
    # If selling_unit is the same as stock_unit, return as-is
    if base_unit.pk == selling_unit.pk:
        return Decimal(str(price))
    
    # Otherwise, convert the price
    return convert_price_for_unit(price, base_unit, selling_unit, item=item)


def bulk_get_prices_for_unit(items, selling_unit, use_selling_price: bool = True) -> dict:
    """
    Efficiently get adjusted prices for multiple items.
    
    Args:
        items: QuerySet or list of Item objects
        selling_unit: Unit to price in
        use_selling_price: If True, use selling_price; if False, use cost_price
        
    Returns:
        Dict mapping item.id to adjusted price (Decimal)
    """
    result = {}
    for item in items:
        result[item.id] = get_item_price_for_unit(item, selling_unit, use_selling_price)
    return result


def validate_unit_conversion_path(from_unit, to_unit, item=None) -> bool:
    """
    Check if a conversion path exists between two units.
    
    Args:
        from_unit: Source unit
        to_unit: Target unit
        item: Optional item for item-specific check
        
    Returns:
        True if conversion is possible, False otherwise
    """
    if not from_unit or not to_unit:
        return False
    
    if from_unit.pk == to_unit.pk:
        return True
    
    factor = get_conversion_factor(from_unit, to_unit, item)
    return factor is not None
