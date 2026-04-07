from decimal import Decimal
from catalog.utils import calculate_line_cogs_with_conversion


def pos_sale_cogs(pos_sale):
    """
    Calculate COGS for a POS sale with unit conversions applied.

    Includes both regular lines and bundle lines.
    """
    total = Decimal('0')

    # Regular sale lines
    for line in pos_sale.lines.select_related('item', 'unit').all():
        cogs = calculate_line_cogs_with_conversion(line.item, line.qty, line.unit)
        total += cogs

    # Bundle lines (PriceList bundles)
    for bundle in pos_sale.bundle_lines.prefetch_related(
        'price_list__items__item', 'price_list__items__unit'
    ).all():
        for pli in bundle.price_list.items.all():
            item_cogs = calculate_line_cogs_with_conversion(
                pli.item, pli.min_qty, pli.unit
            )
            total += item_cogs * bundle.qty_sets

    return total



def sales_order_cogs(sales_order):
    """
    Calculate COGS for a sales order with unit conversions applied.
    
    Includes both regular lines and price list bundle lines.
    """
    total = Decimal('0')
    
    # Regular order lines
    for line in sales_order.lines.select_related('item', 'unit').all():
        cogs = calculate_line_cogs_with_conversion(line.item, line.qty_ordered, line.unit)
        total += cogs
    
    # Price list bundle lines
    for bundle in sales_order.price_list_lines.prefetch_related(
        'price_list__items__item', 'price_list__items__unit'
    ).all():
        for pli in bundle.price_list.items.all():
            item_cogs = calculate_line_cogs_with_conversion(
                pli.item,
                pli.min_qty,
                pli.unit
            )
            # Multiply by qty_multiplier for the bundle
            total += item_cogs * bundle.qty_multiplier
    
    return total



def service_invoice_cogs(invoice):
    """
    Calculate COGS for a service invoice with unit conversions applied.

    Formula: Product Lines COGS + Bundles COGS = Total COGS

    Includes:
      - Product lines (ServiceLine): item cost_price × qty (with unit conversion), scrap excluded
      - Bundle lines (ServiceBundle): each PriceListItem cost_price × min_qty × bundle qty
    Excludes:
      - Other materials (ServiceOtherMaterial): unit_price is the customer-facing selling
        price, not a cost — including it would inflate COGS with revenue figures.
    """
    total = Decimal('0')
    for svc in invoice.customer_services.prefetch_related(
        'lines__item', 'lines__unit',
        'bundles__price_list__items__item', 'bundles__price_list__items__unit',
    ).all():
        # Product lines (skip scrap / waste)
        for line in svc.lines.all():
            if getattr(line, 'is_scrap', False):
                continue
            cogs = calculate_line_cogs_with_conversion(line.item, line.qty, line.unit)
            total += cogs

        # Bundle lines (PriceList bundles)
        for bundle in svc.bundles.all():
            for pli in bundle.price_list.items.all():
                item_cogs = calculate_line_cogs_with_conversion(
                    pli.item, pli.min_qty, pli.unit
                )
                total += item_cogs * bundle.qty

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
