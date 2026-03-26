from decimal import Decimal
from catalog.utils import calculate_line_cogs_with_conversion


def pos_sale_cogs(pos_sale):
    """
    Calculate COGS for a POS sale with unit conversions applied.
    
    Each line's COGS is calculated as:
    - cost_price adjusted for the line's selling unit / item's stock unit
    - multiplied by the quantity ordered in that unit
    """
    total = Decimal('0')
    for line in pos_sale.lines.select_related('item', 'unit').all():
        cogs = calculate_line_cogs_with_conversion(line.item, line.qty, line.unit)
        total += cogs
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
    
    Each service line's COGS is calculated with its unit conversion factor.
    """
    total = Decimal('0')
    for svc in invoice.customer_services.prefetch_related('lines__item', 'lines__unit').all():
        for line in svc.lines.all():
            cogs = calculate_line_cogs_with_conversion(line.item, line.qty, line.unit)
            total += cogs
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
