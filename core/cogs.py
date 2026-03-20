from decimal import Decimal


def pos_sale_cogs(pos_sale):
    total = Decimal('0')
    for line in pos_sale.lines.select_related('item').all():
        total += (line.item.cost_price or Decimal('0')) * line.qty
    return total



def sales_order_cogs(sales_order):
    total = Decimal('0')
    for line in sales_order.lines.select_related('item').all():
        total += (line.item.cost_price or Decimal('0')) * line.qty_ordered
    for bundle in sales_order.price_list_lines.prefetch_related('price_list__items__item').all():
        for pli in bundle.price_list.items.all():
            total += (
                (pli.item.cost_price or Decimal('0'))
                * pli.min_qty
                * bundle.qty_multiplier
            )
    return total



def service_invoice_cogs(invoice):
    total = Decimal('0')
    for svc in invoice.customer_services.prefetch_related('lines__item').all():
        for line in svc.lines.all():
            total += (line.item.cost_price or Decimal('0')) * line.qty
    return total



def compute_invoice_cogs(invoice):
    if invoice.pos_sale_id:
        cogs = pos_sale_cogs(invoice.pos_sale)
    elif invoice.sales_order_id:
        cogs = sales_order_cogs(invoice.sales_order)
    else:
        cogs = service_invoice_cogs(invoice)
    return cogs.quantize(Decimal('0.01'))
