from decimal import Decimal
from catalog.utils import calculate_line_cogs_with_conversion


def pos_sale_cogs(pos_sale):
    """
    Calculate COGS for a POS sale with unit conversions applied.

    Includes both regular lines and bundle lines.
    Gracefully handles missing items (orphaned FKs) by skipping them.
    """
    total = Decimal('0')

    # Regular sale lines
    for line in pos_sale.lines.select_related('item', 'unit').all():
        try:
            if line.item and line.unit:
                cogs = calculate_line_cogs_with_conversion(line.item, line.qty, line.unit)
                total += cogs
        except Exception:
            # Skip lines with missing items or other errors
            continue

    # Bundle lines (PriceList bundles)
    for bundle in pos_sale.bundle_lines.prefetch_related(
        'price_list__items__item', 'price_list__items__unit'
    ).all():
        try:
            for pli in bundle.price_list.items.all():
                if pli.item and pli.unit:
                    item_cogs = calculate_line_cogs_with_conversion(
                        pli.item, pli.min_qty, pli.unit
                    )
                    total += item_cogs * bundle.qty_sets
        except Exception:
            # Skip bundles with missing items or other errors
            continue

    return total



def sales_order_cogs(sales_order):
    """
    Calculate COGS for a sales order with unit conversions applied.
    
    Includes both regular lines and price list bundle lines.
    Gracefully handles missing items (orphaned FKs) by skipping them.
    """
    total = Decimal('0')
    
    # Regular order lines
    for line in sales_order.lines.select_related('item', 'unit').all():
        try:
            if line.item and line.unit:
                cogs = calculate_line_cogs_with_conversion(line.item, line.qty_ordered, line.unit)
                total += cogs
        except Exception:
            # Skip lines with missing items or other errors
            continue
    
    # Price list bundle lines
    for bundle in sales_order.price_list_lines.prefetch_related(
        'price_list__items__item', 'price_list__items__unit'
    ).all():
        try:
            for pli in bundle.price_list.items.all():
                if pli.item and pli.unit:
                    item_cogs = calculate_line_cogs_with_conversion(
                        pli.item,
                        pli.min_qty,
                        pli.unit
                    )
                    # Multiply by qty_multiplier for the bundle
                    total += item_cogs * bundle.qty_multiplier
        except Exception:
            # Skip bundles with missing items or other errors
            continue
    
    return total



def service_invoice_cogs(invoice):
    """
    Calculate COGS for a service invoice with unit conversions applied.

    Formula: Product Lines COGS + Bundles COGS + Other Materials COGS = Total COGS

    Includes:
      - Product lines (ServiceLine): item cost_price × qty (with procurement unit conversion), scrap excluded
      - Bundle lines (ServiceBundle): each PriceListItem cost_price × min_qty × bundle qty
      - Other materials (ServiceOtherMaterial): unit_cost × qty (cost paid to vendor)
    
    NOTE: Services use the procurement unit (stock_unit) for COGS calculation, not the selling unit.
    This is because service parts are consumed from inventory at their procurement rate.
    
    Gracefully handles missing items (orphaned FKs) by skipping them.
    """
    total = Decimal('0')
    for svc in invoice.customer_services.prefetch_related(
        'lines__item', 'lines__unit',
        'bundles__price_list__items__item', 'bundles__price_list__items__unit',
        'other_materials',  # Added to prefetch
    ).all():
        # Product lines (skip scrap / waste)
        for line in svc.lines.all():
            try:
                if getattr(line, 'is_scrap', False):
                    continue
                if line.item:
                    # Services use procurement unit (stock_unit) for COGS, not selling unit
                    procurement_unit = line.item.stock_unit
                    cogs = calculate_line_cogs_with_conversion(line.item, line.qty, procurement_unit)
                    total += cogs
            except Exception:
                # Skip lines with missing items or other errors
                continue

        # Bundle lines (PriceList bundles)
        for bundle in svc.bundles.all():
            try:
                for pli in bundle.price_list.items.all():
                    if pli.item:
                        # Services use procurement unit (stock_unit) for COGS, not selling unit
                        procurement_unit = pli.item.stock_unit
                        item_cogs = calculate_line_cogs_with_conversion(
                            pli.item, pli.min_qty, procurement_unit
                        )
                        total += item_cogs * bundle.qty
            except Exception:
                # Skip bundles with missing items or other errors
                continue
        
        # Other materials - use cost price (unit_cost), not selling price (unit_price)
        for mat in svc.other_materials.all():
            try:
                total += mat.line_cost  # Uses unit_cost * qty
            except Exception:
                # Skip materials with errors
                continue

    return total



def compute_invoice_cogs(invoice):
    """Compute COGS from linked source document with unit conversions."""
    if invoice.pos_sale_id:
        cogs = pos_sale_cogs(invoice.pos_sale)
    elif invoice.sales_order_id:
        cogs = sales_order_cogs(invoice.sales_order)
    else:
        cogs = service_invoice_cogs(invoice)
    return cogs.quantize(Decimal('0.01'))
