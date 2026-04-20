"""
Django management command to check for services with partial payments.
Usage: python manage.py check_partial_payments
"""
from django.core.management.base import BaseCommand
from services.models import CustomerService, ServicePaymentStatus, ServiceStatus
from decimal import Decimal


class Command(BaseCommand):
    help = 'Check for services with partial payments and display their details'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('\n=== Checking for Services with Partial Payments ===\n'))
        
        # Query 1: Services with payment_status = PARTIAL
        partial_status_services = CustomerService.objects.filter(
            payment_status=ServicePaymentStatus.PARTIAL
        ).exclude(status=ServiceStatus.CANCELLED)
        
        self.stdout.write(f'\n1. Services with payment_status=PARTIAL: {partial_status_services.count()}')
        for svc in partial_status_services:
            self.stdout.write(f'   - {svc.service_number}: {svc.customer_name}')
            self.stdout.write(f'     Status: {svc.get_status_display()}')
            self.stdout.write(f'     Payment Status: {svc.get_payment_status_display()}')
            self.stdout.write(f'     Partial Payment Amount: ₱{svc.partial_payment_amount or 0:,.2f}')
            self.stdout.write(f'     Quotation: ₱{svc.quotation_amount:,.2f}')
            self.stdout.write(f'     Has Invoice: {"Yes" if svc.invoice_id else "No"}')
            self.stdout.write(f'     Service Date: {svc.service_date}')
            self.stdout.write('')
        
        # Query 2: Services with partial_payment_amount > 0
        partial_amount_services = CustomerService.objects.filter(
            partial_payment_amount__gt=0,
            partial_payment_amount__isnull=False
        ).exclude(status=ServiceStatus.CANCELLED)
        
        self.stdout.write(f'\n2. Services with partial_payment_amount > 0: {partial_amount_services.count()}')
        for svc in partial_amount_services:
            self.stdout.write(f'   - {svc.service_number}: {svc.customer_name}')
            self.stdout.write(f'     Status: {svc.get_status_display()}')
            self.stdout.write(f'     Payment Status: {svc.get_payment_status_display()}')
            self.stdout.write(f'     Partial Payment Amount: ₱{svc.partial_payment_amount or 0:,.2f}')
            self.stdout.write(f'     Quotation: ₱{svc.quotation_amount:,.2f}')
            self.stdout.write(f'     Has Invoice: {"Yes" if svc.invoice_id else "No"}')
            self.stdout.write(f'     Service Date: {svc.service_date}')
            self.stdout.write('')
        
        # Query 3: Services without invoice and with partial payment
        no_invoice_services = CustomerService.objects.filter(
            partial_payment_amount__gt=0,
            invoice__isnull=True
        ).exclude(status=ServiceStatus.CANCELLED)
        
        self.stdout.write(f'\n3. Services with partial payment and NO invoice: {no_invoice_services.count()}')
        for svc in no_invoice_services:
            self.stdout.write(f'   - {svc.service_number}: {svc.customer_name}')
            self.stdout.write(f'     Status: {svc.get_status_display()}')
            self.stdout.write(f'     Payment Status: {svc.get_payment_status_display()}')
            self.stdout.write(f'     Partial Payment Amount: ₱{svc.partial_payment_amount or 0:,.2f}')
            self.stdout.write(f'     Quotation: ₱{svc.quotation_amount:,.2f}')
            self.stdout.write(f'     Service Date: {svc.service_date}')
            self.stdout.write('')
        
        # Query 4: All services (for comparison)
        all_services = CustomerService.objects.exclude(status=ServiceStatus.CANCELLED)
        self.stdout.write(f'\n4. Total non-cancelled services: {all_services.count()}')
        
        # Summary
        self.stdout.write(self.style.SUCCESS('\n=== Summary ==='))
        self.stdout.write(f'Services with payment_status=PARTIAL: {partial_status_services.count()}')
        self.stdout.write(f'Services with partial_payment_amount > 0: {partial_amount_services.count()}')
        self.stdout.write(f'Services with partial payment and no invoice: {no_invoice_services.count()}')
        self.stdout.write(f'Total non-cancelled services: {all_services.count()}')
        
        if no_invoice_services.count() == 0:
            self.stdout.write(self.style.WARNING('\n⚠️  No services found with partial payments and no invoice!'))
            self.stdout.write(self.style.WARNING('This means either:'))
            self.stdout.write('  1. All services with partial payments have been invoiced')
            self.stdout.write('  2. No services have partial_payment_amount set')
            self.stdout.write('  3. No services have payment_status=PARTIAL')
            self.stdout.write('\nTo add a partial payment to a service:')
            self.stdout.write('  1. Edit the service in the admin or service form')
            self.stdout.write('  2. Set payment_status to "PARTIAL"')
            self.stdout.write('  3. Set partial_payment_amount to the amount received')
            self.stdout.write('  4. Save the service (do NOT complete it yet)')
        else:
            self.stdout.write(self.style.SUCCESS(f'\n✓ Found {no_invoice_services.count()} service(s) that should appear in P&L!'))
        
        self.stdout.write('')
