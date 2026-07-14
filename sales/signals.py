"""
Signals to synchronize Sales Order changes to related Invoices, Deliveries, and Pickups.
"""
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db import transaction

from sales.models import SalesOrder, DeliveryNote, SalesPickup
from core.models import Invoice


@receiver(post_save, sender=SalesOrder)
def sync_sales_order_changes_to_related_documents(sender, instance, created, **kwargs):
    """
    When a Sales Order is updated, synchronize changes to:
    1. Related non-void Invoices
    2. Related Delivery Notes (if not posted)
    3. Related Sales Pickups (if not posted)
    
    Uses on_commit to ensure all related lines (formsets) are saved.
    """
    if created:
        # Skip on creation - only sync on updates
        return
    
    def do_sync():
        # Use transaction to ensure all updates are atomic
        with transaction.atomic():
            # 1. Update related invoices
            _sync_invoices(instance)
            
            # 2. Update related deliveries
            _sync_deliveries(instance)
            
            # 3. Update related pickups
            _sync_pickups(instance)

    # Use on_commit to ensure all formset data is in the DB
    transaction.on_commit(do_sync)


def _sync_invoices(sales_order):
    """
    Synchronize Sales Order changes to related non-void Invoices.
    Updates customer info and delegates lines/totals to the same
    sync_invoice_totals_from_so() helper the posting-time invoice
    creation/update paths use (inventory/automation.py) — bills each line
    at qty_delivered and applies discount_rule/delivery_charge exactly
    once, so an SO edit after invoice creation can never drift back to
    the old qty_ordered/no-discount behavior those paths were fixed to
    avoid (previously this function had its own, separate copy of the
    same logic that never got the fix).
    """
    from audit.models import AuditLog
    from inventory.automation import sync_invoice_totals_from_so

    # Materialise the queryset once to avoid the exists()+iterate double-query
    invoice_list = list(Invoice.objects.filter(
        sales_order=sales_order,
        is_void=False
    ).select_for_update())

    if not invoice_list:
        return

    # Get customer info
    customer_name = sales_order.customer.name if sales_order.customer else ''
    customer_address = getattr(sales_order.customer, 'address', '') if sales_order.customer else ''

    for invoice in invoice_list:
        # Track what changed for audit
        changes = []

        before_subtotal = invoice.subtotal
        before_grand_total = invoice.grand_total

        # Update customer information
        if invoice.customer_name != customer_name:
            changes.append(f"Customer name: '{invoice.customer_name}' → '{customer_name}'")
            invoice.customer_name = customer_name

        if invoice.customer_address != customer_address:
            changes.append(f"Customer address updated")
            invoice.customer_address = customer_address

        invoice.save(update_fields=['customer_name', 'customer_address', 'updated_at'])

        # Recreate invoice lines + totals to match current SO fulfillment
        sync_invoice_totals_from_so(invoice, sales_order)

        if invoice.subtotal != before_subtotal:
            changes.append(f"Subtotal: {before_subtotal} → {invoice.subtotal}")
        if invoice.grand_total != before_grand_total:
            changes.append(f"Grand total: {before_grand_total} → {invoice.grand_total}")

        if changes:
            # Log the sync in audit trail
            AuditLog.objects.create(
                action='UPDATE',
                model_name='Invoice',
                object_id=invoice.id,
                object_repr=str(invoice),
                changes={
                    'source': f'Synced from Sales Order {sales_order.document_number}',
                    'updates': changes
                },
                user=getattr(sales_order, 'updated_by', invoice.created_by),
            )


def _sync_deliveries(sales_order):
    """
    Synchronize Sales Order changes to related Delivery Notes.
    Only updates DRAFT deliveries (not posted ones).
    """
    from audit.models import AuditLog
    from core.models import DocumentStatus
    
    delivery_list = list(DeliveryNote.objects.filter(
        sales_order=sales_order,
        status=DocumentStatus.DRAFT
    ).select_for_update())

    if not delivery_list:
        return
    
    # Get updated info from SO
    shipping_address = sales_order.shipping_address
    delivery_date = sales_order.delivery_date
    customer = sales_order.customer
    warehouse = sales_order.warehouse
    
    for delivery in delivery_list:
        changes = []
        
        # Update shipping address
        if delivery.shipping_address != shipping_address:
            changes.append(f"Shipping address updated")
            delivery.shipping_address = shipping_address
        
        # Update delivery date if SO has one
        if delivery_date and delivery.delivery_date != delivery_date:
            changes.append(f"Delivery date: {delivery.delivery_date} → {delivery_date}")
            delivery.delivery_date = delivery_date
        
        # Update customer
        if delivery.customer_id != customer.id:
            changes.append(f"Customer: {delivery.customer.name} → {customer.name}")
            delivery.customer = customer
        
        # Update warehouse
        if delivery.warehouse_id != warehouse.id:
            changes.append(f"Warehouse: {delivery.warehouse.name} → {warehouse.name}")
            delivery.warehouse = warehouse
        
        # Save delivery and recreate lines
        delivery.save(update_fields=[
            'shipping_address', 'delivery_date', 'customer', 
            'warehouse', 'updated_at'
        ])
        
        # Recreate delivery lines to match current SO
        _recreate_delivery_lines(delivery, sales_order)
        
        if changes:
            # Log the sync
            AuditLog.objects.create(
                action='UPDATE',
                model_name='DeliveryNote',
                object_id=delivery.id,
                object_repr=str(delivery),
                changes={
                    'source': f'Synced from Sales Order {sales_order.document_number}',
                    'updates': changes
                },
                user=getattr(sales_order, 'updated_by', delivery.created_by),
            )


def _recreate_delivery_lines(delivery, sales_order):
    """
    Delete existing delivery lines and recreate them from the current Sales Order.
    Uses the first active location in the delivery warehouse as default.
    """
    from warehouses.models import Location
    from sales.models import DeliveryLine

    delivery.lines.all().delete()

    default_location = Location.objects.filter(
        warehouse=delivery.warehouse, is_active=True
    ).first()

    if not default_location:
        return

    new_lines = []
    for so_line in sales_order.lines.select_related('item', 'unit').all():
        new_lines.append(DeliveryLine(
            delivery=delivery,
            item=so_line.item,
            location=default_location,
            qty=so_line.qty_ordered,
            unit=so_line.unit,
            notes=f'Synced from SO line: {so_line.item.code}',
        ))

    for bundle in sales_order.price_list_lines.select_related('price_list').prefetch_related(
        'price_list__items__item', 'price_list__items__unit'
    ).all():
        for pli in bundle.price_list.items.select_related('item', 'unit').all():
            qty = pli.min_qty * bundle.qty_multiplier
            if qty <= 0:
                continue
            new_lines.append(DeliveryLine(
                delivery=delivery,
                item=pli.item,
                location=default_location,
                qty=qty,
                unit=pli.unit,
                notes=f'Synced from bundle {bundle.price_list.name}',
            ))

    if new_lines:
        DeliveryLine.objects.bulk_create(new_lines)


def _sync_pickups(sales_order):
    """
    Synchronize Sales Order changes to related Sales Pickups.
    Only updates DRAFT pickups (not posted ones).
    """
    from audit.models import AuditLog
    from core.models import DocumentStatus
    
    pickup_list = list(SalesPickup.objects.filter(
        sales_order=sales_order,
        status=DocumentStatus.DRAFT
    ).select_for_update())

    if not pickup_list:
        return
    
    # Get updated info from SO
    pickup_date = sales_order.delivery_date  # Use delivery_date as pickup_date
    customer = sales_order.customer
    warehouse = sales_order.warehouse
    
    for pickup in pickup_list:
        changes = []
        
        # Update pickup date if SO has delivery_date
        if pickup_date and pickup.pickup_date != pickup_date:
            changes.append(f"Pickup date: {pickup.pickup_date} → {pickup_date}")
            pickup.pickup_date = pickup_date
        
        # Update customer
        if pickup.customer_id != customer.id:
            changes.append(f"Customer: {pickup.customer.name} → {customer.name}")
            pickup.customer = customer
        
        # Update warehouse
        if pickup.warehouse_id != warehouse.id:
            changes.append(f"Warehouse: {pickup.warehouse.name} → {warehouse.name}")
            pickup.warehouse = warehouse
        
        # Save pickup and recreate lines
        pickup.save(update_fields=[
            'pickup_date', 'customer', 'warehouse', 'updated_at'
        ])
        
        # Recreate pickup lines to match current SO
        _recreate_pickup_lines(pickup, sales_order)
        
        if changes:
            # Log the sync
            AuditLog.objects.create(
                action='UPDATE',
                model_name='SalesPickup',
                object_id=pickup.id,
                object_repr=str(pickup),
                changes={
                    'source': f'Synced from Sales Order {sales_order.document_number}',
                    'updates': changes
                },
                user=getattr(sales_order, 'updated_by', pickup.created_by),
            )


def _recreate_pickup_lines(pickup, sales_order):
    """
    Delete existing pickup lines and recreate them from the current Sales Order.
    Uses the first active location in the pickup warehouse as default.
    """
    from warehouses.models import Location
    from sales.models import SalesPickupLine

    pickup.lines.all().delete()

    default_location = Location.objects.filter(
        warehouse=pickup.warehouse, is_active=True
    ).first()

    if not default_location:
        return

    new_lines = []
    for so_line in sales_order.lines.select_related('item', 'unit').all():
        new_lines.append(SalesPickupLine(
            pickup=pickup,
            item=so_line.item,
            location=default_location,
            qty=so_line.qty_ordered,
            unit=so_line.unit,
            batch_number=getattr(so_line, 'batch_number', '') or '',
            serial_number=getattr(so_line, 'serial_number', '') or '',
            notes=f'Synced from SO line: {so_line.item.code}',
        ))

    for bundle in sales_order.price_list_lines.select_related('price_list').prefetch_related(
        'price_list__items__item', 'price_list__items__unit'
    ).all():
        for pli in bundle.price_list.items.select_related('item', 'unit').all():
            qty = pli.min_qty * bundle.qty_multiplier
            if qty <= 0:
                continue
            new_lines.append(SalesPickupLine(
                pickup=pickup,
                item=pli.item,
                location=default_location,
                qty=qty,
                unit=pli.unit,
                notes=f'Synced from bundle {bundle.price_list.name}',
            ))

    if new_lines:
        SalesPickupLine.objects.bulk_create(new_lines)


