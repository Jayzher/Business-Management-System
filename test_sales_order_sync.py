#!/usr/bin/env python
"""
Test script for Sales Order synchronization signals.
Run with: python manage.py shell < test_sales_order_sync.py
"""

import os
import django
from decimal import Decimal

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'business_management.settings')
django.setup()

from sales.models import SalesOrder, DeliveryNote, SalesPickup
from core.models import Invoice, InvoiceLine, DocumentStatus
from audit.models import AuditLog
from django.contrib.auth import get_user_model

User = get_user_model()


def test_invoice_sync():
    """Test that invoice updates when Sales Order changes."""
    print("\n" + "="*60)
    print("TEST 1: Invoice Synchronization")
    print("="*60)
    
    # Find a sales order with a non-void invoice
    so = SalesOrder.objects.filter(
        invoices__isnull=False,
        invoices__is_void=False
    ).first()
    
    if not so:
        print("❌ No Sales Order with invoice found. Skipping test.")
        return
    
    invoice = so.invoices.filter(is_void=False).first()
    
    print(f"\n📋 Testing with Sales Order: {so.document_number}")
    print(f"📄 Related Invoice: {invoice.invoice_number}")
    
    # Store original values
    original_delivery_charge = so.delivery_charge
    original_invoice_total = invoice.grand_total
    original_line_count = invoice.lines.count()
    
    print(f"\n📊 Before Update:")
    print(f"   SO Delivery Charge: {original_delivery_charge}")
    print(f"   Invoice Grand Total: {original_invoice_total}")
    print(f"   Invoice Line Count: {original_line_count}")
    
    # Update the Sales Order
    new_delivery_charge = original_delivery_charge + Decimal('50.00')
    so.delivery_charge = new_delivery_charge
    so.save()
    
    # Refresh invoice from database
    invoice.refresh_from_db()
    
    print(f"\n📊 After Update:")
    print(f"   SO Delivery Charge: {so.delivery_charge}")
    print(f"   Invoice Grand Total: {invoice.grand_total}")
    print(f"   Invoice Line Count: {invoice.lines.count()}")
    
    # Verify the sync worked
    expected_total = original_invoice_total + Decimal('50.00')
    if invoice.grand_total == expected_total:
        print(f"\n✅ SUCCESS: Invoice grand total updated correctly!")
        print(f"   Expected: {expected_total}, Got: {invoice.grand_total}")
    else:
        print(f"\n❌ FAILED: Invoice grand total mismatch!")
        print(f"   Expected: {expected_total}, Got: {invoice.grand_total}")
    
    # Check audit log
    recent_log = AuditLog.objects.filter(
        model_name='Invoice',
        object_id=invoice.id
    ).order_by('-timestamp').first()
    
    if recent_log:
        print(f"\n📝 Audit Log Created:")
        print(f"   Action: {recent_log.action}")
        print(f"   Changes: {recent_log.changes}")
    
    # Restore original value
    so.delivery_charge = original_delivery_charge
    so.save()
    print(f"\n🔄 Restored original delivery charge")


def test_delivery_sync():
    """Test that draft delivery updates when Sales Order changes."""
    print("\n" + "="*60)
    print("TEST 2: Delivery Note Synchronization")
    print("="*60)
    
    # Find a sales order with a draft delivery
    so = SalesOrder.objects.filter(
        deliveries__isnull=False,
        deliveries__status=DocumentStatus.DRAFT
    ).first()
    
    if not so:
        print("❌ No Sales Order with draft delivery found. Skipping test.")
        return
    
    delivery = so.deliveries.filter(status=DocumentStatus.DRAFT).first()
    
    print(f"\n📋 Testing with Sales Order: {so.document_number}")
    print(f"🚚 Related Delivery: {delivery.document_number}")
    
    # Store original values
    original_address = so.shipping_address
    original_delivery_address = delivery.shipping_address
    
    print(f"\n📊 Before Update:")
    print(f"   SO Shipping Address: {original_address[:50]}...")
    print(f"   Delivery Shipping Address: {original_delivery_address[:50]}...")
    
    # Update the Sales Order
    new_address = "Updated Test Address - 123 New Street, Test City"
    so.shipping_address = new_address
    so.save()
    
    # Refresh delivery from database
    delivery.refresh_from_db()
    
    print(f"\n📊 After Update:")
    print(f"   SO Shipping Address: {so.shipping_address[:50]}...")
    print(f"   Delivery Shipping Address: {delivery.shipping_address[:50]}...")
    
    # Verify the sync worked
    if delivery.shipping_address == new_address:
        print(f"\n✅ SUCCESS: Delivery shipping address updated correctly!")
    else:
        print(f"\n❌ FAILED: Delivery shipping address not updated!")
    
    # Check audit log
    recent_log = AuditLog.objects.filter(
        model_name='DeliveryNote',
        object_id=delivery.id
    ).order_by('-timestamp').first()
    
    if recent_log:
        print(f"\n📝 Audit Log Created:")
        print(f"   Action: {recent_log.action}")
        print(f"   Changes: {recent_log.changes}")
    
    # Restore original value
    so.shipping_address = original_address
    so.save()
    print(f"\n🔄 Restored original shipping address")


def test_pickup_sync():
    """Test that draft pickup updates when Sales Order changes."""
    print("\n" + "="*60)
    print("TEST 3: Sales Pickup Synchronization")
    print("="*60)
    
    # Find a sales order with a draft pickup
    so = SalesOrder.objects.filter(
        pickups__isnull=False,
        pickups__status=DocumentStatus.DRAFT
    ).first()
    
    if not so:
        print("❌ No Sales Order with draft pickup found. Skipping test.")
        return
    
    pickup = so.pickups.filter(status=DocumentStatus.DRAFT).first()
    
    print(f"\n📋 Testing with Sales Order: {so.document_number}")
    print(f"📦 Related Pickup: {pickup.document_number}")
    
    # Store original values
    original_date = so.delivery_date
    original_pickup_date = pickup.pickup_date
    
    print(f"\n📊 Before Update:")
    print(f"   SO Delivery Date: {original_date}")
    print(f"   Pickup Date: {original_pickup_date}")
    
    # Update the Sales Order
    from datetime import date, timedelta
    new_date = date.today() + timedelta(days=7)
    so.delivery_date = new_date
    so.save()
    
    # Refresh pickup from database
    pickup.refresh_from_db()
    
    print(f"\n📊 After Update:")
    print(f"   SO Delivery Date: {so.delivery_date}")
    print(f"   Pickup Date: {pickup.pickup_date}")
    
    # Verify the sync worked
    if pickup.pickup_date == new_date:
        print(f"\n✅ SUCCESS: Pickup date updated correctly!")
    else:
        print(f"\n❌ FAILED: Pickup date not updated!")
    
    # Check audit log
    recent_log = AuditLog.objects.filter(
        model_name='SalesPickup',
        object_id=pickup.id
    ).order_by('-timestamp').first()
    
    if recent_log:
        print(f"\n📝 Audit Log Created:")
        print(f"   Action: {recent_log.action}")
        print(f"   Changes: {recent_log.changes}")
    
    # Restore original value
    so.delivery_date = original_date
    so.save()
    print(f"\n🔄 Restored original delivery date")


def test_posted_delivery_not_synced():
    """Test that posted deliveries are NOT updated."""
    print("\n" + "="*60)
    print("TEST 4: Posted Delivery Should NOT Sync")
    print("="*60)
    
    # Find a sales order with a posted delivery
    so = SalesOrder.objects.filter(
        deliveries__isnull=False,
        deliveries__status=DocumentStatus.POSTED
    ).first()
    
    if not so:
        print("❌ No Sales Order with posted delivery found. Skipping test.")
        return
    
    delivery = so.deliveries.filter(status=DocumentStatus.POSTED).first()
    
    print(f"\n📋 Testing with Sales Order: {so.document_number}")
    print(f"🚚 Related Posted Delivery: {delivery.document_number}")
    
    # Store original values
    original_address = delivery.shipping_address
    
    print(f"\n📊 Before Update:")
    print(f"   Delivery Shipping Address: {original_address[:50]}...")
    print(f"   Delivery Status: {delivery.status}")
    
    # Update the Sales Order
    new_address = "This Should NOT Update Posted Delivery"
    so.shipping_address = new_address
    so.save()
    
    # Refresh delivery from database
    delivery.refresh_from_db()
    
    print(f"\n📊 After Update:")
    print(f"   Delivery Shipping Address: {delivery.shipping_address[:50]}...")
    
    # Verify the sync did NOT happen
    if delivery.shipping_address == original_address:
        print(f"\n✅ SUCCESS: Posted delivery was NOT updated (correct behavior)!")
    else:
        print(f"\n❌ FAILED: Posted delivery was updated (should not happen)!")


def test_void_invoice_not_synced():
    """Test that void invoices are NOT updated."""
    print("\n" + "="*60)
    print("TEST 5: Void Invoice Should NOT Sync")
    print("="*60)
    
    # Find a sales order with a void invoice
    so = SalesOrder.objects.filter(
        invoices__isnull=False,
        invoices__is_void=True
    ).first()
    
    if not so:
        print("❌ No Sales Order with void invoice found. Skipping test.")
        return
    
    invoice = so.invoices.filter(is_void=True).first()
    
    print(f"\n📋 Testing with Sales Order: {so.document_number}")
    print(f"📄 Related Void Invoice: {invoice.invoice_number}")
    
    # Store original values
    original_total = invoice.grand_total
    
    print(f"\n📊 Before Update:")
    print(f"   Invoice Grand Total: {original_total}")
    print(f"   Invoice is_void: {invoice.is_void}")
    
    # Update the Sales Order
    so.delivery_charge = Decimal('999.99')
    so.save()
    
    # Refresh invoice from database
    invoice.refresh_from_db()
    
    print(f"\n📊 After Update:")
    print(f"   Invoice Grand Total: {invoice.grand_total}")
    
    # Verify the sync did NOT happen
    if invoice.grand_total == original_total:
        print(f"\n✅ SUCCESS: Void invoice was NOT updated (correct behavior)!")
    else:
        print(f"\n❌ FAILED: Void invoice was updated (should not happen)!")


def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("SALES ORDER SYNCHRONIZATION SIGNAL TESTS")
    print("="*60)
    
    try:
        test_invoice_sync()
        test_delivery_sync()
        test_pickup_sync()
        test_posted_delivery_not_synced()
        test_void_invoice_not_synced()
        
        print("\n" + "="*60)
        print("ALL TESTS COMPLETED")
        print("="*60)
        
    except Exception as e:
        print(f"\n❌ ERROR: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    main()
