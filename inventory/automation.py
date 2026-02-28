"""
Document automation service — auto-creates downstream documents when upstream
documents are approved or posted.

Flow:
  PO Approved  →  auto-create GRN (DRAFT)
  SO Approved  →  auto-create Delivery Note (DRAFT) + auto-create Invoice
  DN Posted    →  auto-create Invoice (if SO linked and no invoice yet)
  POS Posted   →  auto-create Invoice (if not already exists)
"""
from datetime import date
from decimal import Decimal
from django.db import transaction
from django.utils import timezone

from inventory.services import generate_document_number


@transaction.atomic
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


@transaction.atomic
def auto_create_delivery_from_so(so, user):
    """
    When an SO is approved, auto-create a Delivery Note (DRAFT)
    with lines matching the SO lines.
    Returns the created DN or None if one already exists.
    """
    from sales.models import SalesOrder, DeliveryNote, DeliveryLine
    from warehouses.models import Location

    # Check if a DN already exists for this SO
    existing = DeliveryNote.objects.filter(sales_order=so).first()
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
        qty_remaining = so_line.qty_ordered - so_line.qty_delivered
        if qty_remaining <= 0:
            continue
        DeliveryLine.objects.create(
            delivery=dn,
            item=so_line.item,
            location=default_location,
            qty=qty_remaining,
            unit=so_line.unit,
            notes=f'From SO line: {so_line.item.code}',
        )

    return dn


@transaction.atomic
def auto_create_invoice_from_so(so, user):
    """
    Auto-create an Invoice from a Sales Order when it is approved.
    Returns the created Invoice or existing one.
    """
    from core.models import Invoice, InvoiceLine

    existing = Invoice.objects.filter(sales_order=so).first()
    if existing:
        return existing

    # Generate invoice number
    last = Invoice.objects.order_by('-id').first()
    num = (last.id + 1) if last else 1
    inv_number = f"{num:06d}"

    subtotal = sum(l.line_total for l in so.lines.all())

    inv = Invoice.objects.create(
        invoice_number=inv_number,
        date=date.today(),
        sales_order=so,
        customer_name=so.customer.name if so.customer else '',
        customer_address=getattr(so.customer, 'address', '') if so.customer else '',
        subtotal=subtotal,
        grand_total=subtotal,
        notes=f'Auto-created from {so.document_number}',
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

    return inv


@transaction.atomic
def auto_create_invoice_from_delivery(delivery, user):
    """
    Auto-create an Invoice when a Delivery Note is posted.
    Links to the SO if available.
    Returns the created Invoice or existing one.
    """
    from core.models import Invoice, InvoiceLine

    # If SO linked, check if invoice already exists for that SO
    if delivery.sales_order:
        existing = Invoice.objects.filter(sales_order=delivery.sales_order).first()
        if existing:
            return existing

    last = Invoice.objects.order_by('-id').first()
    num = (last.id + 1) if last else 1
    inv_number = f"{num:06d}"

    # Calculate totals from SO lines if available, else from delivery lines
    if delivery.sales_order:
        subtotal = sum(l.line_total for l in delivery.sales_order.lines.all())
        inv = Invoice.objects.create(
            invoice_number=inv_number,
            date=date.today(),
            sales_order=delivery.sales_order,
            customer_name=delivery.customer.name if delivery.customer else '',
            customer_address=getattr(delivery.customer, 'address', '') if delivery.customer else '',
            subtotal=subtotal,
            grand_total=subtotal,
            is_paid=False,
            notes=f'Auto-created from delivery {delivery.document_number}',
            created_by=user,
        )
        for line in delivery.sales_order.lines.select_related('item', 'unit'):
            InvoiceLine.objects.create(
                invoice=inv,
                item_code=line.item.code,
                item_name=line.item.name,
                qty=line.qty_ordered,
                unit=line.unit.abbreviation,
                unit_price=line.unit_price,
                line_total=line.line_total,
            )
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


@transaction.atomic
def auto_create_invoice_from_pos_sale(sale, user):
    """
    Auto-create an Invoice when a POS Sale is posted.
    Returns the created Invoice or existing one.
    """
    from core.models import Invoice, InvoiceLine

    existing = Invoice.objects.filter(pos_sale=sale).first()
    if existing:
        return existing

    last = Invoice.objects.order_by('-id').first()
    num = (last.id + 1) if last else 1
    inv_number = f"{num:06d}"

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

    return inv
