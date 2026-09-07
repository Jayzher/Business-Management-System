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
    if hasattr(pos_sale, '_prefetched_objects_cache') and 'lines' in pos_sale._prefetched_objects_cache:
        lines = pos_sale.lines.all()
    else:
        lines = pos_sale.lines.select_related('item', 'item__default_unit', 'unit').all()

    for line in lines:
        try:
            if line.item and line.unit:
                cogs = calculate_line_cogs_with_conversion(line.item, line.qty, line.unit)
                total += cogs
        except Exception:
            # Skip lines with missing items or other errors
            continue

    # Bundle lines (PriceList bundles)
    if hasattr(pos_sale, '_prefetched_objects_cache') and 'bundle_lines' in pos_sale._prefetched_objects_cache:
        bundles = pos_sale.bundle_lines.all()
    else:
        bundles = pos_sale.bundle_lines.prefetch_related(
            'price_list__items__item', 'price_list__items__item__default_unit', 'price_list__items__unit'
        ).all()

    for bundle in bundles:
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



def sales_order_cogs(sales_order, qty_field='qty_delivered'):
    """
    Calculate COGS for a sales order with unit conversions applied.

    Includes both regular lines and price list bundle lines.
    Gracefully handles missing items (orphaned FKs) by skipping them.

    qty_field selects which quantity the regular lines are costed at:
      - 'qty_delivered' (default) — what a fulfillment-built invoice actually
        bills (see _create_invoice_lines_from_so), so a partially-fulfilled
        SO's COGS stays in the same scope as its revenue.
      - 'qty_ordered' — used by compute_invoice_cogs for a direct SO invoice
        that was billed and paid before ANY delivery/pickup was posted (so
        every line's qty_delivered is 0). There the invoice charged the full
        order, so COGS must too, or it collapses to 0 against real revenue.
    Bundle lines have no partial-fulfilment tracking and are always billed in
    full, so they're costed in full regardless of qty_field.
    """
    total = Decimal('0')

    # Regular order lines — costed at the chosen quantity field (see docstring).
    if hasattr(sales_order, '_prefetched_objects_cache') and 'lines' in sales_order._prefetched_objects_cache:
        lines = sales_order.lines.all()
    else:
        lines = sales_order.lines.select_related('item', 'item__default_unit', 'unit').all()

    for line in lines:
        try:
            if line.item and line.unit:
                qty = getattr(line, qty_field, None) or Decimal('0')
                cogs = calculate_line_cogs_with_conversion(line.item, qty, line.unit)
                total += cogs
        except Exception:
            # Skip lines with missing items or other errors
            continue

    # Price list bundle lines
    if hasattr(sales_order, '_prefetched_objects_cache') and 'price_list_lines' in sales_order._prefetched_objects_cache:
        bundles = sales_order.price_list_lines.all()
    else:
        bundles = sales_order.price_list_lines.prefetch_related(
            'price_list__items__item', 'price_list__items__item__default_unit', 'price_list__items__unit'
        ).all()

    for bundle in bundles:
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
      - Product lines (ServiceLine): item cost_price × qty (with unit conversion), scrap excluded
      - Bundle lines (ServiceBundle): each PriceListItem cost_price × min_qty × bundle qty
      - Other materials (ServiceOtherMaterial): unit_cost × qty (cost paid to vendor)
    
    Gracefully handles missing items (orphaned FKs) by skipping them.
    """
    total = Decimal('0')
    if hasattr(invoice, '_prefetched_objects_cache') and 'customer_services' in invoice._prefetched_objects_cache:
        services = invoice.customer_services.all()
    else:
        services = invoice.customer_services.prefetch_related(
            'lines__item', 'lines__item__default_unit', 'lines__unit',
            'bundles__price_list__items__item', 'bundles__price_list__items__item__default_unit',
            'bundles__price_list__items__unit',
            'other_materials',  # Added to prefetch
        ).all()

    for svc in services:
        # Product lines (skip scrap / waste)
        for line in svc.lines.all():
            try:
                if getattr(line, 'is_scrap', False):
                    continue
                if line.item and line.unit:
                    cogs = calculate_line_cogs_with_conversion(line.item, line.qty, line.unit)
                    total += cogs
            except Exception:
                # Skip lines with missing items or other errors
                continue

        # Bundle lines (PriceList bundles)
        for bundle in svc.bundles.all():
            try:
                for pli in bundle.price_list.items.all():
                    if pli.item and pli.unit:
                        item_cogs = calculate_line_cogs_with_conversion(
                            pli.item, pli.min_qty, pli.unit
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



def _sales_order_has_posted_fulfillment(sales_order):
    """True if the SO has any POSTED delivery or pickup with non-zero delivered quantity.
    When False, an invoice for this SO was necessarily billed at qty_ordered (a direct SO
    invoice paid before any fulfillment), so its COGS must be costed at qty_ordered too."""
    from core.models import DocumentStatus
    if hasattr(sales_order, '_prefetched_objects_cache') and 'deliveries' in sales_order._prefetched_objects_cache and 'pickups' in sales_order._prefetched_objects_cache:
        has_posted = (
            any(d.status == DocumentStatus.POSTED for d in sales_order.deliveries.all())
            or any(p.status == DocumentStatus.POSTED for p in sales_order.pickups.all())
        )
    else:
        has_posted = (
            sales_order.deliveries.filter(status=DocumentStatus.POSTED).exists()
            or sales_order.pickups.filter(status=DocumentStatus.POSTED).exists()
        )
    if not has_posted:
        return False
    # If lines have no delivered quantity (qty_delivered_total == 0), using qty_delivered
    # will collapse COGS to 0 against real invoice revenue. So require qty_delivered_total > 0.
    return sales_order.qty_delivered_total > 0



def compute_invoice_cogs(invoice):
    """Compute COGS from the linked source document with unit conversions.

    For SO-linked invoices, COGS is costed at qty_delivered when the SO has
    real (posted) fulfillment with non-zero delivered quantity, and at qty_ordered otherwise.
    If costing at qty_delivered evaluates to 0 but qty_ordered yields a positive COGS,
    it falls back to qty_ordered to ensure COGS is never wrongly zeroed out for billed orders.
    """
    if invoice.pos_sale_id:
        cogs = pos_sale_cogs(invoice.pos_sale)
    elif invoice.sales_order_id:
        so = invoice.sales_order
        qty_field = 'qty_delivered' if _sales_order_has_posted_fulfillment(so) else 'qty_ordered'
        cogs = sales_order_cogs(so, qty_field=qty_field)
        if cogs == Decimal('0'):
            ordered_cogs = sales_order_cogs(so, qty_field='qty_ordered')
            if ordered_cogs > Decimal('0'):
                cogs = ordered_cogs
    else:
        cogs = service_invoice_cogs(invoice)
    return cogs.quantize(Decimal('0.01'))

