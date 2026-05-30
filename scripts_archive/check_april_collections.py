#!/usr/bin/env python
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from core.models import InvoicePayment, Invoice
from datetime import date
from django.db.models import Sum

# Get payments in April
payments = InvoicePayment.objects.filter(date__gte=date(2026, 4, 1), date__lt=date(2026, 5, 1))
print(f'Payments in April: {payments.count()}')
print(f'Total paid: ₱{payments.aggregate(Sum("amount"))["amount__sum"] or 0:,.2f}')

# Get invoices paid in April
invoices = Invoice.objects.filter(invoicepayment__in=payments).distinct()
print(f'\nInvoices paid in April: {invoices.count()}')

# Check invoice dates
print('\nInvoice dates:')
for inv in invoices[:10]:
    print(f'  {inv.invoice_number}: {inv.date} - ₱{inv.grand_total:,.2f}')

# Check if there are invoices from previous months
print('\nInvoices by month:')
for inv in invoices:
    print(f'  {inv.invoice_number}: {inv.date.strftime("%B %Y")} - ₱{inv.grand_total:,.2f}')
