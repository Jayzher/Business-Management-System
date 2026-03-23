"""
Catalog utilities for unit conversions and price calculations.
Flexible logic for handling unit conversion factors across all selling scenarios.
"""
from decimal import Decimal
from typing import Optional, Union, Tuple


def _lookup_conversion_record(from_unit, to_unit, item=None) -> Tuple:
    """
    Look up a UnitConversion record between two units.

    Returns (conversion_record, is_reverse) where is_reverse=True means the stored
    record goes to_unit→from_unit and the effective factor is 1/record.factor.

    Priority: item-specific direct → global direct → item-specific reverse → global reverse.
    """
    from catalog.models import UnitConversion

    if item is not None:
        c = UnitConversion.objects.filter(
            from_unit=from_unit, to_unit=to_unit, item=item, is_active=True
        ).first()
        if c:
            return c, False

    c = UnitConversion.objects.filter(
        from_unit=from_unit, to_unit=to_unit, item__isnull=True, is_active=True
    ).first()
    if c:
        return c, False

    if item is not None:
        c = UnitConversion.objects.filter(
            from_unit=to_unit, to_unit=from_unit, item=item, is_active=True
        ).first()
        if c and c.factor != 0:
            return c, True

    c = UnitConversion.objects.filter(
        from_unit=to_unit, to_unit=from_unit, item__isnull=True, is_active=True
    ).first()
    if c and c.factor != 0:
        return c, True

    return None, False


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

    conv, is_reverse = _lookup_conversion_record(from_unit, to_unit, item)
    if conv is None:
        return None
    return Decimal('1') / conv.factor if is_reverse else conv.factor


def convert_price_for_unit(
    base_price: Union[Decimal, float, str],
    base_unit,
    selling_unit,
    item=None,
    round_places: int = 4,
    use_conversion_price: bool = True,
) -> Decimal:
    """
    Convert a price from one unit to another based on conversion factors.

    When *use_conversion_price* is True (the default, used for selling prices):
      - If the matching UnitConversion record has ``conversion_price`` set **and**
        the match is direct (not a reverse lookup), that explicit price is returned
        instead of dividing base_price by the factor.
      - This lets you set a per-converted-unit price independently of the ratio.
        Example: Roll→ft factor=5, conversion_price=30 → price per ft = 30 (not 100/5=20).

    When *use_conversion_price* is False (used for COGS):
      - Always performs factor-based division: base_price / factor.
      - ``conversion_price`` is never used for cost calculations.

    Args:
        base_price: The base price in the base_unit
        base_unit: The unit the base_price is denominated in
        selling_unit: The unit we want to price in
        item: Optional item for item-specific conversions
        round_places: Decimal places to round result to
        use_conversion_price: If True, prefer explicit conversion_price over factor calc

    Returns:
        Decimal price adjusted for the selling_unit
    """
    if not base_unit or not selling_unit:
        return Decimal(str(base_price)).quantize(Decimal(10) ** -round_places)

    if base_unit.pk == selling_unit.pk:
        return Decimal(str(base_price)).quantize(Decimal(10) ** -round_places)

    base_price_dec = Decimal(str(base_price))

    conv, is_reverse = _lookup_conversion_record(base_unit, selling_unit, item)

    if conv is None:
        return base_price_dec.quantize(Decimal(10) ** -round_places)

    if use_conversion_price and not is_reverse and conv.conversion_price is not None:
        return conv.conversion_price.quantize(Decimal(10) ** -round_places)

    factor = Decimal('1') / conv.factor if is_reverse else conv.factor

    if factor == 0:
        return base_price_dec.quantize(Decimal(10) ** -round_places)

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


def get_item_cogs_for_unit(item, selling_unit) -> Decimal:
    """
    Get the item's cost price adjusted for a specific selling unit.
    
    This is the inverse operation of selling price conversion - it calculates
    the cost of goods sold when the item is sold in a different unit than
    its stock unit.
    
    Args:
        item: Item object
        selling_unit: Unit the item is being sold in
        
    Returns:
        Decimal cost price in the specified unit
        
    Example:
        cost_price = $5 per Piece
        stock_unit = Piece
        selling_unit = Foot
        1 Piece = 19.7 Feet
        Result: $5 / 19.7 ≈ $0.254 per Foot
    """
    if not item or not selling_unit:
        return Decimal('0')
    
    cost_price = item.cost_price or Decimal('0')
    
    # Get the stock unit for this item
    base_unit = item.stock_unit
    
    # If selling_unit is the same as stock_unit, return as-is
    if base_unit.pk == selling_unit.pk:
        return Decimal(str(cost_price))
    
    # COGS always uses factor-based calculation, never conversion_price
    return convert_price_for_unit(
        cost_price, base_unit, selling_unit, item=item, use_conversion_price=False
    )


def calculate_line_cogs_with_conversion(line_item, qty_ordered, selling_unit, item=None) -> Decimal:
    """
    Calculate COGS for a line with unit conversion applied.
    
    Args:
        line_item: The item object
        qty_ordered: Quantity ordered in the selling_unit
        selling_unit: The unit the quantity is in
        item: Optional item parameter (defaults to line_item)
        
    Returns:
        Decimal COGS amount
    """
    if not line_item or not selling_unit:
        return Decimal('0')
    
    if item is None:
        item = line_item
    
    # Get the cost price adjusted for the selling unit
    unit_cost = get_item_cogs_for_unit(item, selling_unit)
    
    # Multiply by quantity
    cogs = unit_cost * Decimal(str(qty_ordered))
    
    return cogs
