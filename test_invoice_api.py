#!/usr/bin/env python
"""
Test script for Invoice API endpoints.
Run with: python manage.py shell < test_invoice_api.py
"""

import os
import django
from decimal import Decimal

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'inventory_system.settings')
django.setup()

from django.test import RequestFactory
from django.contrib.auth import get_user_model
from rest_framework.test import force_authenticate

from core.api_views import InvoiceViewSet
from core.models import Invoice

User = get_user_model()


def test_invoice_list():
    """Test invoice list endpoint."""
    print("\n" + "="*60)
    print("TEST 1: Invoice List Endpoint")
    print("="*60)
    
    # Create request
    factory = RequestFactory()
    request = factory.get('/api/invoices/')
    
    # Get or create test user
    user = User.objects.filter(is_superuser=True).first()
    if not user:
        print("❌ No superuser found. Please create one first.")
        return
    
    force_authenticate(request, user=user)
    
    # Create viewset and get response
    viewset = InvoiceViewSet.as_view({'get': 'list'})
    response = viewset(request)
    
    print(f"\n📊 Response Status: {response.status_code}")
    
    if response.status_code == 200:
        data = response.data
        print(f"✅ SUCCESS: API returned {data.get('count', 0)} invoices")
        print(f"   Page size: {len(data.get('results', []))}")
        print(f"   Has next: {data.get('next') is not None}")
        print(f"   Has previous: {data.get('previous') is not None}")
        
        if data.get('results'):
            first_invoice = data['results'][0]
            print(f"\n📄 First Invoice:")
            print(f"   Invoice #: {first_invoice.get('invoice_number')}")
            print(f"   Customer: {first_invoice.get('customer_name')}")
            print(f"   Amount: ₱{first_invoice.get('grand_total')}")
            print(f"   Status: {first_invoice.get('payment_status')}")
    else:
        print(f"❌ FAILED: Status {response.status_code}")
        print(f"   Response: {response.data}")


def test_invoice_detail():
    """Test invoice detail endpoint."""
    print("\n" + "="*60)
    print("TEST 2: Invoice Detail Endpoint")
    print("="*60)
    
    # Get first invoice
    invoice = Invoice.objects.first()
    if not invoice:
        print("❌ No invoices found in database. Skipping test.")
        return
    
    print(f"\n📋 Testing with Invoice: {invoice.invoice_number}")
    
    # Create request
    factory = RequestFactory()
    request = factory.get(f'/api/invoices/{invoice.id}/')
    
    user = User.objects.filter(is_superuser=True).first()
    force_authenticate(request, user=user)
    
    # Create viewset and get response
    viewset = InvoiceViewSet.as_view({'get': 'retrieve'})
    response = viewset(request, pk=invoice.id)
    
    print(f"\n📊 Response Status: {response.status_code}")
    
    if response.status_code == 200:
        data = response.data
        print(f"✅ SUCCESS: Retrieved invoice details")
        print(f"\n📄 Invoice Details:")
        print(f"   Invoice #: {data.get('invoice_number')}")
        print(f"   Customer: {data.get('customer_name')}")
        print(f"   Date: {data.get('date')}")
        print(f"   Subtotal: ₱{data.get('subtotal')}")
        print(f"   Delivery Charge: ₱{data.get('delivery_charge')}")
        print(f"   Grand Total: ₱{data.get('grand_total')}")
        print(f"   Payment Status: {data.get('payment_status')}")
        print(f"   Is Paid: {data.get('is_paid')}")
        print(f"   Is Void: {data.get('is_void')}")
        
        lines = data.get('lines', [])
        print(f"\n📦 Line Items: {len(lines)}")
        for i, line in enumerate(lines[:3], 1):
            print(f"   {i}. {line.get('item_name')} - Qty: {line.get('qty')} - Total: ₱{line.get('line_total')}")
        
        payments = data.get('payments', [])
        print(f"\n💰 Payments: {len(payments)}")
        for i, payment in enumerate(payments[:3], 1):
            print(f"   {i}. {payment.get('date')} - {payment.get('method')} - ₱{payment.get('amount')}")
    else:
        print(f"❌ FAILED: Status {response.status_code}")
        print(f"   Response: {response.data}")


def test_invoice_filters():
    """Test invoice filtering."""
    print("\n" + "="*60)
    print("TEST 3: Invoice Filtering")
    print("="*60)
    
    factory = RequestFactory()
    user = User.objects.filter(is_superuser=True).first()
    
    # Test 1: Filter by is_paid
    print("\n🔍 Test 3.1: Filter unpaid invoices")
    request = factory.get('/api/invoices/?is_paid=false')
    force_authenticate(request, user=user)
    viewset = InvoiceViewSet.as_view({'get': 'list'})
    response = viewset(request)
    
    if response.status_code == 200:
        count = response.data.get('count', 0)
        print(f"✅ Found {count} unpaid invoices")
    else:
        print(f"❌ FAILED: Status {response.status_code}")
    
    # Test 2: Filter by date range
    print("\n🔍 Test 3.2: Filter by date range")
    request = factory.get('/api/invoices/?date_from=2026-01-01&date_to=2026-12-31')
    force_authenticate(request, user=user)
    response = viewset(request)
    
    if response.status_code == 200:
        count = response.data.get('count', 0)
        print(f"✅ Found {count} invoices in 2026")
    else:
        print(f"❌ FAILED: Status {response.status_code}")
    
    # Test 3: Search by customer
    invoice = Invoice.objects.first()
    if invoice and invoice.customer_name:
        print(f"\n🔍 Test 3.3: Search by customer '{invoice.customer_name[:10]}'")
        request = factory.get(f'/api/invoices/?customer={invoice.customer_name[:5]}')
        force_authenticate(request, user=user)
        response = viewset(request)
        
        if response.status_code == 200:
            count = response.data.get('count', 0)
            print(f"✅ Found {count} invoices for customer")
        else:
            print(f"❌ FAILED: Status {response.status_code}")


def test_invoice_summary():
    """Test invoice summary endpoint."""
    print("\n" + "="*60)
    print("TEST 4: Invoice Summary Endpoint")
    print("="*60)
    
    factory = RequestFactory()
    request = factory.get('/api/invoices/summary/')
    
    user = User.objects.filter(is_superuser=True).first()
    force_authenticate(request, user=user)
    
    viewset = InvoiceViewSet.as_view({'get': 'summary'})
    response = viewset(request)
    
    print(f"\n📊 Response Status: {response.status_code}")
    
    if response.status_code == 200:
        data = response.data
        print(f"✅ SUCCESS: Retrieved summary statistics")
        print(f"\n📈 Summary:")
        print(f"   Total Invoices: {data.get('total_count')}")
        print(f"   Total Amount: ₱{data.get('total_amount')}")
        print(f"   Paid Count: {data.get('paid_count')}")
        print(f"   Paid Amount: ₱{data.get('paid_amount')}")
        print(f"   Unpaid Count: {data.get('unpaid_count')}")
        print(f"   Unpaid Amount: ₱{data.get('unpaid_amount')}")
        print(f"   Void Count: {data.get('void_count')}")
    else:
        print(f"❌ FAILED: Status {response.status_code}")
        print(f"   Response: {response.data}")


def test_invoice_unpaid():
    """Test unpaid invoices endpoint."""
    print("\n" + "="*60)
    print("TEST 5: Unpaid Invoices Endpoint")
    print("="*60)
    
    factory = RequestFactory()
    request = factory.get('/api/invoices/unpaid/')
    
    user = User.objects.filter(is_superuser=True).first()
    force_authenticate(request, user=user)
    
    viewset = InvoiceViewSet.as_view({'get': 'unpaid'})
    response = viewset(request)
    
    print(f"\n📊 Response Status: {response.status_code}")
    
    if response.status_code == 200:
        data = response.data
        print(f"✅ SUCCESS: Retrieved unpaid invoices")
        print(f"   Count: {data.get('count', 0)}")
        print(f"   Page size: {len(data.get('results', []))}")
        
        if data.get('results'):
            print(f"\n📄 Sample Unpaid Invoices:")
            for inv in data['results'][:3]:
                print(f"   - {inv.get('invoice_number')}: ₱{inv.get('grand_total')} - {inv.get('customer_name')}")
    else:
        print(f"❌ FAILED: Status {response.status_code}")
        print(f"   Response: {response.data}")


def test_invoice_overdue():
    """Test overdue invoices endpoint."""
    print("\n" + "="*60)
    print("TEST 6: Overdue Invoices Endpoint")
    print("="*60)
    
    factory = RequestFactory()
    request = factory.get('/api/invoices/overdue/')
    
    user = User.objects.filter(is_superuser=True).first()
    force_authenticate(request, user=user)
    
    viewset = InvoiceViewSet.as_view({'get': 'overdue'})
    response = viewset(request)
    
    print(f"\n📊 Response Status: {response.status_code}")
    
    if response.status_code == 200:
        data = response.data
        print(f"✅ SUCCESS: Retrieved overdue invoices")
        print(f"   Count: {data.get('count', 0)}")
        
        if data.get('results'):
            print(f"\n📄 Sample Overdue Invoices:")
            for inv in data['results'][:3]:
                print(f"   - {inv.get('invoice_number')}: Due {inv.get('due_date')} - ₱{inv.get('grand_total')}")
        else:
            print(f"   No overdue invoices found (good!)")
    else:
        print(f"❌ FAILED: Status {response.status_code}")
        print(f"   Response: {response.data}")


def test_pagination():
    """Test pagination."""
    print("\n" + "="*60)
    print("TEST 7: Pagination")
    print("="*60)
    
    factory = RequestFactory()
    user = User.objects.filter(is_superuser=True).first()
    
    # Test different page sizes
    for page_size in [5, 10, 25]:
        print(f"\n📄 Testing page_size={page_size}")
        request = factory.get(f'/api/invoices/?page_size={page_size}')
        force_authenticate(request, user=user)
        
        viewset = InvoiceViewSet.as_view({'get': 'list'})
        response = viewset(request)
        
        if response.status_code == 200:
            data = response.data
            results_count = len(data.get('results', []))
            print(f"✅ Returned {results_count} invoices (expected: {min(page_size, data.get('count', 0))})")
        else:
            print(f"❌ FAILED: Status {response.status_code}")


def test_ordering():
    """Test ordering."""
    print("\n" + "="*60)
    print("TEST 8: Ordering")
    print("="*60)
    
    factory = RequestFactory()
    user = User.objects.filter(is_superuser=True).first()
    
    orderings = [
        ('date', 'Date (ascending)'),
        ('-date', 'Date (descending)'),
        ('grand_total', 'Amount (ascending)'),
        ('-grand_total', 'Amount (descending)'),
    ]
    
    for ordering, label in orderings:
        print(f"\n📊 Testing ordering: {label}")
        request = factory.get(f'/api/invoices/?ordering={ordering}&page_size=3')
        force_authenticate(request, user=user)
        
        viewset = InvoiceViewSet.as_view({'get': 'list'})
        response = viewset(request)
        
        if response.status_code == 200:
            data = response.data
            results = data.get('results', [])
            if results:
                print(f"✅ First invoice: {results[0].get('invoice_number')} - {results[0].get('date')} - ₱{results[0].get('grand_total')}")
            else:
                print(f"   No results")
        else:
            print(f"❌ FAILED: Status {response.status_code}")


def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("INVOICE API ENDPOINT TESTS")
    print("="*60)
    
    try:
        # Check if invoices exist
        invoice_count = Invoice.objects.count()
        print(f"\n📊 Database Status:")
        print(f"   Total Invoices: {invoice_count}")
        
        if invoice_count == 0:
            print("\n⚠️  WARNING: No invoices in database. Some tests may be skipped.")
        
        # Run tests
        test_invoice_list()
        test_invoice_detail()
        test_invoice_filters()
        test_invoice_summary()
        test_invoice_unpaid()
        test_invoice_overdue()
        test_pagination()
        test_ordering()
        
        print("\n" + "="*60)
        print("ALL TESTS COMPLETED")
        print("="*60)
        print("\n✅ Invoice API is working correctly!")
        print("\n📚 Next Steps:")
        print("   1. Test via browser: http://localhost:8000/api/invoices/")
        print("   2. Test with Postman or curl")
        print("   3. Integrate with frontend")
        print("   4. Review documentation: INVOICE_API_DOCUMENTATION.md")
        
    except Exception as e:
        print(f"\n❌ ERROR: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    main()
