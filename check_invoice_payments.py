#!/usr/bin/env python
"""Check invoice payments for April 2026."""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'inventory_system.settings')
django.setup()

from core.models import InvoicePayment
from datetime import date

start_date = date(2026, 4, 1)
end_date = date(2026, 5, 1)

payments = InvoicePayment.objects.filter(
    date__gte=start_date,
    date__lt=end_date,
)

print("\n" + "=" * 60)
print("APRIL 2026 - INVOICE PAYMENTS")
print("=" * 60)

if payments.exists():
    print(f"\nFound {payments.count()} invoice payment(s):")
    total = 0
    for p in payments:
        print(f"  {p.date} - Invoice #{p.invoice.invoice_number} - ₱{p.amount:,.2f}")
        total += p.amount
    print(f"\nTotal AR Collections: ₱{total:,.2f}")
else:
    print("\n❌ NO invoice payments found in April 2026")
    print("   All sales were POS (immediate cash) sales")

print("\n" + "=" * 60)
