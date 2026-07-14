"""
Document automation service — auto-creates downstream documents when upstream
documents are approved or posted.

Correct flow:
  PO Approved   →  auto-create GRN (DRAFT)
  SO Approved
    DELIVER      →  auto-create Delivery Note (DRAFT)   [no invoice yet]
    PICKUP       →  auto-create Sales Pickup (DRAFT)    [no invoice yet]
  DN Posted      →  auto-create Invoice (if SO linked and no non-void invoice)
  Pickup Posted  →  auto-create Invoice (if SO linked and no non-void invoice)
  DN Cancelled (POSTED) →  void linked Invoice + reverse qty_delivered
  Pickup Cancelled      →  void linked Invoice + reverse qty_delivered
  POS Sale Posted       →  auto-create Invoice

NOTE: Invoice is intentionally NOT created at SO approval — it is only
created when goods are physically fulfilled (DN or Pickup posted).
"""
from datetime import date
from decimal import Decimal
from django.db import transaction
from django.utils import timezone

from django.db.models import Max
from inventory.services import generate_document_number, _WRITE_DB


def _generate_invoice_number():
    """
    Generate the next invoice number as a zero-padded 6-digit string.
    Uses MAX(id) across ALL invoice rows (including any soft-deleted) so the
    number is always strictly increasing and never collides.
    Must be called inside a transaction.atomic() block.
    """
    from core.models import Invoice
    result = Invoice.objects.aggregate(max_id=Max('id'))
    next_num = (result['max_id'] or 0) + 1
    return f"{next_num:06d}"


@transaction.atomic(using=_WRITE_DB)
def auto_create_grn_from_po(po, user):
    """
    When a PO is approved, auto-create a Goods Receipt Note (DRAFT)
    with lines matching the PO lines.
    Returns the created GRN or None if one already exists.
    """
    from procurement.models import PurchaseOrder, GoodsReceipt, GoodsReceiptLine
    from warehouses.models import Location

    # Check if a GRN already exists for this PO
    existing = GoodsReceipt.objects.filter(purchase_order=po).first()
    if existing:
        return existing

    # Get the first location in the PO warehouse
    default_location = Location.objects.filter(
        warehouse=po.warehouse, is_active=True
    ).first()
    if not default_location:
        return None  # Cannot create GRN without a location

    grn = GoodsReceipt(
        document_number=generate_document_number('GRN', GoodsReceipt),
        purchase_order=po,
        supplier=po.supplier,
        warehouse=po.warehouse,
        receipt_date=date.today(),
        notes=f'Auto-created from {po.document_number}',
        created_by=user,
    )
    grn.save()

    for po_line in po.lines.select_related('item', 'unit').all():
        qty_remaining = po_line.qty_ordered - po_line.qty_received
        if qty_remaining <= 0:
            continue
        GoodsReceiptLine.objects.create(
            goods_receipt=grn,
            item=po_line.item,
            location=default_location,
            qty=qty_remaining,
            unit=po_line.unit,
            notes=f'From PO line: {po_line.item.code}',
        )

    return grn


@transaction.atomic(using=_WRITE_DB)
def auto_create_delivery_from_so(so, user):
    """
    When an SO is approved, auto-create a Delivery Note (DRAFT)
    with lines matching the SO lines.
    Returns the created DN or None if one already exists.
    """
    from sales.models import SalesOrder, DeliveryNote, DeliveryLine
    from warehouses.models import Location

    if getattr(so, 'fulfillment_type', None) != 'DELIVER':
        return None

    # Check if a non-cancelled DN already exists for this SO
    from core.models import DocumentStatus
    existing = DeliveryNote.objects.filter(
        sales_order=so,
    ).exclude(status=DocumentStatus.CANCELLED).first()
    if existing:
        return existing

    # Get the first location in the SO warehouse
    default_location = Location.objects.filter(
        warehouse=so.warehouse, is_active=True
    ).first()
    if not default_location:
        return None

    dn = DeliveryNote(
        document_number=generate_document_number('DN', DeliveryNote),
        sales_order=so,
        customer=so.customer,
        warehouse=so.warehouse,
        delivery_date=so.delivery_date or date.today(),
        shipping_address=so.shipping_address,
        notes=f'Auto-created from {so.document_number}',
        created_by=user,
    )
    dn.save()

    for so_line in so.lines.select_related('item', 'unit').all():
        DeliveryLine.objects.create(
            delivery=dn,
            item=so_line.item,
            location=default_location,
            qty=so_line.qty_ordered,
            unit=so_line.unit,
            notes=f'From SO line: {so_line.item.code}',
        )

    for bundle in so.price_list_lines.select_related('price_list').prefetch_related(
        'price_list__items__item', 'price_list__items__unit'
    ).all():
        for pli in bundle.price_list.items.select_related('item', 'unit').all():
            qty = pli.min_qty * bundle.qty_multiplier
            if qty <= 0:
                continue
            DeliveryLine.objects.create(
                delivery=dn,
                item=pli.item,
                location=default_location,
                qty=qty,
                unit=pli.unit,
                notes=f'From bundle {bundle.price_list.name}',
            )

    return dn


@transaction.atomic(using=_WRITE_DB)
def auto_create_pickup_from_so(so, user):
    """
    When an SO is approved with PICKUP fulfillment, auto-create a SalesPickup (DRAFT)
    with lines matching the SO lines.
    Returns the created Pickup or None if one already exists or fulfillment_type is not PICKUP.
    """
    from sales.models import SalesOrder, SalesPickup, SalesPickupLine
    from warehouses.models import Location

    if getattr(so, 'fulfillment_type', None) != 'PICKUP':
        return None

    from core.models import DocumentStatus
    existing = SalesPickup.objects.filter(
        sales_order=so,
    ).exclude(status=DocumentStatus.CANCELLED).first()
    if existing:
        return existing

    default_location = Location.objects.filter(
        warehouse=so.warehouse, is_active=True
    ).first()
    if not default_location:
        return None

    pickup = SalesPickup(
        document_number=generate_document_number('PU', SalesPickup),
        sales_order=so,
        customer=so.customer,
        warehouse=so.warehouse,
        pickup_date=so.delivery_date or date.today(),
        pickup_by='',
        notes=f'Auto-created from {so.document_number}',
        created_by=user,
    )
    pickup.save()

    for so_line in so.lines.select_related('item', 'unit').all():
        SalesPickupLine.objects.create(
            pickup=pickup,
            item=so_line.item,
            location=default_location,
            qty=so_line.qty_ordered,
            unit=so_line.unit,
            batch_number=getattr(so_line, 'batch_number', '') or '',
            serial_number=getattr(so_line, 'serial_number', '') or '',
            notes=f'From SO line: {so_line.item.code}',
        )

    for bundle in so.price_list_lines.select_related('price_list').prefetch_related(
        'price_list__items__item', 'price_list__items__unit'
    ).all():
        for pli in bundle.price_list.items.select_related('item', 'unit').all():
            qty = pli.min_qty * bundle.qty_multiplier
            if qty <= 0:
                continue
            SalesPickupLine.objects.create(
                pickup=pickup,
                item=pli.item,
                location=default_location,
                qty=qty,
                unit=pli.unit,
                notes=f'From bundle {bundle.price_list.name}',
            )

    return pickup


@transaction.atomic(using=_WRITE_DB)
def auto_create_invoice_from_so(so, user):
    """
    Auto-create an Invoice directly from a Sales Order (standalone / on-demand).
    NOT called at SO approval — invoice is normally created when the
    fulfillment document (DN or Pickup) is posted.
    Returns the created Invoice or the existing non-void one.
    """
    from core.models import Invoice, InvoiceLine

    existing = Invoice.objects.filter(sales_order=so, is_void=False).first()
    if existing:
        return existing

    inv_number = _generate_invoice_number()

    subtotal = sum(l.line_total for l in so.lines.all())
    for bundle in so.price_list_lines.all():
        subtotal += bundle.bundle_total

    inv = Invoice.objects.create(
        invoice_number=inv_number,
        date=date.today(),
        sales_order=so,
        customer_name=so.customer.name if so.customer else '',
        customer_address=getattr(so.customer, 'address', '') if so.customer else '',
        subtotal=subtotal,
        grand_total=subtotal,
        notes=f'Auto-created from SO {so.document_number}',
        created_by=user,
    )

    for line in so.lines.select_related('item', 'unit'):
        InvoiceLine.objects.create(
            invoice=inv,
            item_code=line.item.code,
            item_name=line.item.name,
            qty=line.qty_ordered,
            unit=line.unit.abbreviation,
            unit_price=line.unit_price,
            line_total=line.line_total,
        )

    for bundle in so.price_list_lines.select_related('price_list').all():
        InvoiceLine.objects.create(
            invoice=inv,
            item_code='BUNDLE',
            item_name=bundle.price_list.name,
            qty=bundle.qty_multiplier,
            unit='bundle',
            unit_price=bundle.bundle_subtotal,
            discount=bundle.bundle_discount_amount if hasattr(bundle, 'bundle_discount_amount') else Decimal('0'),
            line_total=bundle.bundle_total,
        )

    return inv


def _create_invoice_lines_from_so(invoice, so):
    """
    Create InvoiceLine rows for an SO's lines and bundles, billing each line
    at the quantity actually delivered/picked up so far (`qty_delivered`),
    not the full ordered quantity — so a partial fulfillment only invoices
    what has actually shipped. A line with nothing delivered yet is skipped
    entirely (it will appear once a later delivery/pickup ships some of it).

    The per-unit price reflects the SO line's own discount proportionally:
    effective_unit_price = line_total / qty_ordered, so a fully-delivered
    line (qty_delivered == qty_ordered) bills identically to before.

    Bundle lines have no partial-fulfillment tracking anywhere in the
    system, so they're still billed in full — a known, separate limitation.

    Returns the number of InvoiceLine rows created.
    """
    from core.models import InvoiceLine

    count = 0
    for line in so.lines.select_related('item', 'unit'):
        if line.qty_ordered <= 0 or line.qty_delivered <= 0:
            continue
        effective_unit_price = line.line_total / line.qty_ordered
        InvoiceLine.objects.create(
            invoice=invoice,
            item_code=line.item.code,
            item_name=line.item.name,
            qty=line.qty_delivered,
            unit=line.unit.abbreviation,
            unit_price=effective_unit_price,
            line_total=effective_unit_price * line.qty_delivered,
        )
        count += 1

    for bundle in so.price_list_lines.select_related('price_list').all():
        InvoiceLine.objects.create(
            invoice=invoice,
            item_code='BUNDLE',
            item_name=bundle.price_list.name,
            qty=bundle.qty_multiplier,
            unit='bundle',
            unit_price=bundle.bundle_subtotal,
            discount=bundle.bundle_discount_amount if hasattr(bundle, 'bundle_discount_amount') else Decimal('0'),
            line_total=bundle.bundle_total,
        )
        count += 1
    return count


def sync_invoice_totals_from_so(invoice, so):
    """
    Recompute an SO-linked invoice's lines and totals from the current state
    of the SO — the single source of truth for "what does this SO's invoice
    look like". Used both by the posting-time create/update paths below and
    by sales/signals.py when the SO itself is edited after the invoice
    already exists, so the two never drift out of sync with each other
    (an earlier version of that signal re-derived the same invoice with its
    own, separate — and outdated — logic).

    Bills each line at qty_delivered (not qty_ordered, see
    _create_invoice_lines_from_so) and applies the SO's order-level
    discount_rule and delivery_charge exactly once, mirroring
    SalesOrder.grand_total's own formula so the invoice and the order it
    came from always agree once fully delivered.

    Does NOT touch customer_name/customer_address — callers set those from
    their own source (the delivery/pickup/SO) before calling this.

    Returns the net-new InvoiceLine count (for "N new items" messaging).
    """
    previous_line_count = invoice.lines.count()
    invoice.lines.all().delete()
    new_lines_count = _create_invoice_lines_from_so(invoice, so)
    new_lines_count = max(new_lines_count - previous_line_count, 0)

    subtotal = sum((l.line_total for l in invoice.lines.all()), Decimal('0'))
    delivery_charge = so.delivery_charge or Decimal('0')
    discount = getattr(so, 'discount_rule_order_amount', Decimal('0'))
    grand_total = max(subtotal - discount, Decimal('0')) + delivery_charge

    invoice.subtotal = subtotal
    invoice.delivery_charge = delivery_charge
    invoice.grand_total = grand_total
    invoice.save(update_fields=['subtotal', 'delivery_charge', 'grand_total', 'updated_at'])
    return new_lines_count


@transaction.atomic(using=_WRITE_DB)
def auto_create_invoice_from_pickup(pickup, user):
    """
    Auto-create or UPDATE an Invoice when a Sales Pickup is posted.
    Uses a select_for_update lock on the SO to prevent concurrent duplicate invoices.

    IDEMPOTENT: If invoice exists, updates it with any new items from the SO.
    Returns the created or updated Invoice.
    """
    from core.models import Invoice, InvoiceLine
    import logging
    logger = logging.getLogger(__name__)

    if pickup.sales_order:
        # Lock the SO row so concurrent posts for the same SO wait for this transaction
        from sales.models import SalesOrder
        SalesOrder.objects.select_for_update().filter(pk=pickup.sales_order_id).first()

        # Check for existing non-void invoice linked to this SO
        # Use select_for_update to lock the invoice row as well
        existing = Invoice.objects.select_for_update().filter(
            sales_order=pickup.sales_order,
            is_void=False
        ).first()

        if existing:
            logger.info(f"Found existing invoice {existing.invoice_number} for SO {pickup.sales_order.document_number}, updating it")
            # UPDATE existing invoice to match current SO
            so = pickup.sales_order

            # Update invoice header
            existing.customer_name = pickup.customer.name if pickup.customer else ''
            existing.customer_address = getattr(pickup.customer, 'address', '') if pickup.customer else ''
            existing.save(update_fields=['customer_name', 'customer_address', 'updated_at'])

            # RECREATE invoice lines + totals to match current fulfillment
            new_lines_count = sync_invoice_totals_from_so(existing, so)

            logger.info(f"Updated invoice {existing.invoice_number} with {new_lines_count} new lines")
            # Mark that this invoice was updated (for view to display message)
            existing._was_updated = True
            existing._new_lines_count = new_lines_count

            return existing
        else:
            logger.info(f"No existing invoice found for SO {pickup.sales_order.document_number}, creating new one")

    inv_number = _generate_invoice_number()

    if pickup.sales_order:
        so = pickup.sales_order
        inv = Invoice.objects.create(
            invoice_number=inv_number,
            date=date.today(),
            sales_order=so,
            customer_name=pickup.customer.name if pickup.customer else '',
            customer_address=getattr(pickup.customer, 'address', '') if pickup.customer else '',
            subtotal=Decimal('0'),
            grand_total=Decimal('0'),
            is_paid=False,
            notes=f'Auto-created from pickup {pickup.document_number}',
            created_by=user,
        )
        sync_invoice_totals_from_so(inv, so)
    else:
        # No SO linked — create basic invoice from pickup lines
        inv = Invoice.objects.create(
            invoice_number=inv_number,
            date=date.today(),
            customer_name=pickup.customer.name if pickup.customer else '',
            customer_address=getattr(pickup.customer, 'address', '') if pickup.customer else '',
            subtotal=Decimal('0'),
            grand_total=Decimal('0'),
            notes=f'Auto-created from pickup {pickup.document_number}',
            created_by=user,
        )
        for line in pickup.lines.select_related('item', 'unit'):
            InvoiceLine.objects.create(
                invoice=inv,
                item_code=line.item.code,
                item_name=line.item.name,
                qty=line.qty,
                unit=line.unit.abbreviation,
                unit_price=Decimal('0'),
                line_total=Decimal('0'),
            )

    return inv


@transaction.atomic(using=_WRITE_DB)
def auto_create_invoice_from_delivery(delivery, user):
    """
    Auto-create or UPDATE an Invoice when a Delivery Note is posted.
    Uses a select_for_update lock on the SO to prevent concurrent duplicate invoices.
    
    IDEMPOTENT: If invoice exists, updates it with any new items from the SO.
    Returns the created or updated Invoice.
    """
    from core.models import Invoice, InvoiceLine
    import logging
    logger = logging.getLogger(__name__)

    if delivery.sales_order:
        # Lock the SO row so concurrent posts for the same SO wait for this transaction
        from sales.models import SalesOrder
        SalesOrder.objects.select_for_update().filter(pk=delivery.sales_order_id).first()
        
        # Check for existing non-void invoice linked to this SO
        # Use select_for_update to lock the invoice row as well
        existing = Invoice.objects.select_for_update().filter(
            sales_order=delivery.sales_order, 
            is_void=False
        ).first()
        
        if existing:
            logger.info(f"Found existing invoice {existing.invoice_number} for SO {delivery.sales_order.document_number}, updating it")
            # UPDATE existing invoice to match current SO
            so = delivery.sales_order

            # Update invoice header
            existing.customer_name = delivery.customer.name if delivery.customer else ''
            existing.customer_address = getattr(delivery.customer, 'address', '') if delivery.customer else ''
            existing.save(update_fields=['customer_name', 'customer_address', 'updated_at'])

            # RECREATE invoice lines + totals to match current fulfillment
            new_lines_count = sync_invoice_totals_from_so(existing, so)

            logger.info(f"Updated invoice {existing.invoice_number} with {new_lines_count} new lines")
            # Mark that this invoice was updated (for view to display message)
            existing._was_updated = True
            existing._new_lines_count = new_lines_count

            return existing
        else:
            logger.info(f"No existing invoice found for SO {delivery.sales_order.document_number}, creating new one")

    inv_number = _generate_invoice_number()

    # Calculate totals from SO lines if available, else from delivery lines
    if delivery.sales_order:
        so = delivery.sales_order
        inv = Invoice.objects.create(
            invoice_number=inv_number,
            date=date.today(),
            sales_order=so,
            customer_name=delivery.customer.name if delivery.customer else '',
            customer_address=getattr(delivery.customer, 'address', '') if delivery.customer else '',
            subtotal=Decimal('0'),
            grand_total=Decimal('0'),
            is_paid=False,
            notes=f'Auto-created from delivery {delivery.document_number}',
            created_by=user,
        )
        sync_invoice_totals_from_so(inv, so)
    else:
        # No SO linked — create basic invoice from delivery lines
        inv = Invoice.objects.create(
            invoice_number=inv_number,
            date=date.today(),
            customer_name=delivery.customer.name if delivery.customer else '',
            customer_address=getattr(delivery.customer, 'address', '') if delivery.customer else '',
            subtotal=Decimal('0'),
            grand_total=Decimal('0'),
            notes=f'Auto-created from delivery {delivery.document_number}',
            created_by=user,
        )
        for line in delivery.lines.select_related('item', 'unit'):
            InvoiceLine.objects.create(
                invoice=inv,
                item_code=line.item.code,
                item_name=line.item.name,
                qty=line.qty,
                unit=line.unit.abbreviation,
                unit_price=Decimal('0'),
                line_total=Decimal('0'),
            )

    return inv


@transaction.atomic(using=_WRITE_DB)
def auto_create_invoice_from_pos_sale(sale, user):
    """
    Auto-create an Invoice when a POS Sale is posted.
    Returns the created Invoice or existing one.
    """
    from core.models import Invoice, InvoiceLine

    existing = Invoice.objects.filter(pos_sale=sale).first()
    if existing:
        return existing

    inv_number = _generate_invoice_number()

    inv = Invoice.objects.create(
        invoice_number=inv_number,
        date=date.today(),
        pos_sale=sale,
        customer_name=sale.customer.name if sale.customer else 'Walk-in Customer',
        customer_address=getattr(sale.customer, 'address', '') if sale.customer else '',
        subtotal=sale.subtotal,
        discount_total=sale.discount_total,
        tax_total=sale.tax_total,
        grand_total=sale.grand_total,
        is_paid=True,
        notes='Auto-created from POS sale',
        created_by=user,
    )

    for line in sale.lines.select_related('item', 'unit'):
        InvoiceLine.objects.create(
            invoice=inv,
            item_code=line.item.code,
            item_name=line.item.name,
            qty=line.qty,
            unit=line.unit.abbreviation,
            unit_price=line.unit_price,
            discount=line.discount_amount,
            line_total=line.line_total,
        )

    for bundle_line in sale.bundle_lines.select_related('price_list'):
        InvoiceLine.objects.create(
            invoice=inv,
            item_code='BUNDLE',
            item_name=bundle_line.price_list.name,
            qty=bundle_line.qty_sets,
            unit='bundle',
            unit_price=bundle_line.unit_price,
            line_total=bundle_line.line_total,
        )

    return inv
