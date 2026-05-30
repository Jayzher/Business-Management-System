"""
Signals to synchronize Sales Order changes to related Invoices, Deliveries, and Pickups.
"""
from decimal import Decimal
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.db import transaction

from sales.models import SalesOrder, DeliveryNote, SalesPickup
from core.models import Invoice, InvoiceLine


@receiver(post_save, sender=SalesOrder)
def sync_sales_order_changes_to_related_documents(sender, instance, created, **kwargs):
    """
    When a Sales Order is updated, synchronize changes to:
    1. Related non-void Invoices
    2. Related Delivery Notes (if not posted)
    3. Related Sales Pickups (if not posted)
    """
    if created:
        # Skip on creation - only sync on updates
        return
    
    # Use transaction to ensure all updates are atomic
    with transaction.atomic():
        # 1. Update related invoices
        _sync_invoices(instance)
        
        # 2. Update related deliveries
        _sync_deliveries(instance)
        
        # 3. Update related pickups
        _sync_pickups(instance)


def _sync_invoices(sales_order):
    """
    Synchronize Sales Order changes to related non-void Invoices.
    Updates customer info, financial totals, and line items.
    """
    from audit.models import AuditLog
    
    # Find all non-void invoices linked to this SO
    invoices = Invoice.objects.filter(
        sales_order=sales_order,
        is_void=False
    ).select_for_update()
    
    if not invoices.exists():
        return
    
    # Calculate totals from SO
    subtotal = Decimal('0')
    for line in sales_order.lines.all():
        subtotal += line.line_total
    
    for bundle in sales_order.price_list_lines.all():
        subtotal += bundle.bundle_total
    
    delivery_charge = sales_order.delivery_charge or Decimal('0')
    grand_total = subtotal + delivery_charge
    
    # Get customer info
    customer_name = sales_order.customer.name if sales_order.customer else ''
    customer_address = getattr(sales_order.customer, 'address', '') if sales_order.customer else ''
    
    for invoice in invoices:
        # Track what changed for audit
        changes = []
        
        # Update customer information
        if invoice.customer_name != customer_name:
            changes.append(f"Customer name: '{invoice.customer_name}' → '{customer_name}'")
            invoice.customer_name = customer_name
        
        if invoice.customer_address != customer_address:
            changes.append(f"Customer address updated")
            invoice.customer_address = customer_address
        
        # Update financial totals
        if invoice.subtotal != subtotal:
            changes.append(f"Subtotal: {invoice.subtotal} → {subtotal}")
            invoice.subtotal = subtotal
        
        if invoice.delivery_charge != delivery_charge:
            changes.append(f"Delivery charge: {invoice.delivery_charge} → {delivery_charge}")
            invoice.delivery_charge = delivery_charge
        
        if invoice.grand_total != grand_total:
            changes.append(f"Grand total: {invoice.grand_total} → {grand_total}")
            invoice.grand_total = grand_total
        
        # Save invoice if there were changes
        if changes:
            invoice.save(update_fields=[
                'customer_name', 'customer_address', 'subtotal', 
                'delivery_charge', 'grand_total', 'updated_at'
            ])
            
            # Recreate invoice lines to match current SO
            _recreate_invoice_lines(invoice, sales_order)
            
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


def _recreate_invoice_lines(invoice, sales_order):
    """
    Delete existing invoice lines and recreate them from the current Sales Order.
    """
    # Delete existing lines
    invoice.lines.all().delete()
    
    # Recreate from SO lines
    for line in sales_order.lines.select_related('item', 'unit').all():
        InvoiceLine.objects.create(
            invoice=invoice,
            item_code=line.item.code,
            item_name=line.item.name,
            qty=line.qty_ordered,
            unit=line.unit.abbreviation,
            unit_price=line.unit_price,
            discount=line.discount_amount,
            line_total=line.line_total,
        )
    
    # Add bundle lines
    for bundle in sales_order.price_list_lines.select_related('price_list').all():
        InvoiceLine.objects.create(
            invoice=invoice,
            item_code='BUNDLE',
            item_name=bundle.price_list.name,
            qty=bundle.qty_multiplier,
            unit='bundle',
            unit_price=bundle.bundle_subtotal,
            discount=bundle.bundle_discount_amount,
            line_total=bundle.bundle_total,
        )


def _sync_deliveries(sales_order):
    """
    Synchronize Sales Order changes to related Delivery Notes.
    Only updates DRAFT deliveries (not posted ones).
    """
    from audit.models import AuditLog
    from core.models import DocumentStatus
    
    # Find all draft deliveries linked to this SO
    deliveries = DeliveryNote.objects.filter(
        sales_order=sales_order,
        status=DocumentStatus.DRAFT
    ).select_for_update()
    
    if not deliveries.exists():
        return
    
    # Get updated info from SO
    shipping_address = sales_order.shipping_address
    delivery_date = sales_order.delivery_date
    customer = sales_order.customer
    warehouse = sales_order.warehouse
    
    for delivery in deliveries:
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
        
        # Save if there were changes
        if changes:
            delivery.save(update_fields=[
                'shipping_address', 'delivery_date', 'customer', 
                'warehouse', 'updated_at'
            ])
            
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


def _sync_pickups(sales_order):
    """
    Synchronize Sales Order changes to related Sales Pickups.
    Only updates DRAFT pickups (not posted ones).
    """
    from audit.models import AuditLog
    from core.models import DocumentStatus
    
    # Find all draft pickups linked to this SO
    pickups = SalesPickup.objects.filter(
        sales_order=sales_order,
        status=DocumentStatus.DRAFT
    ).select_for_update()
    
    if not pickups.exists():
        return
    
    # Get updated info from SO
    pickup_date = sales_order.delivery_date  # Use delivery_date as pickup_date
    customer = sales_order.customer
    warehouse = sales_order.warehouse
    
    for pickup in pickups:
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
        
        # Save if there were changes
        if changes:
            pickup.save(update_fields=[
                'pickup_date', 'customer', 'warehouse', 'updated_at'
            ])
            
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


@receiver(post_save, sender=SalesOrder)
def log_sales_order_update(sender, instance, created, **kwargs):
    """
    Log Sales Order updates to audit trail.
    """
    from audit.models import AuditLog
    
    if not created:
        # Log the update
        AuditLog.objects.create(
            action='UPDATE',
            model_name='SalesOrder',
            object_id=instance.id,
            object_repr=str(instance),
            changes={
                'message': f"Sales Order {instance.document_number} updated - changes will sync to related documents"
            },
            user=getattr(instance, 'updated_by', instance.created_by),
        )
