#!/usr/bin/env python
"""Quick script to check AR collections data for April 2026."""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'inventory_system.settings')
django.setup()

from cashflow.models import MonthlyCashflowSummary

s = MonthlyCashflowSummary.objects.get(year=2026, month=4)

print("\n" + "=" * 60)
print("APRIL 2026 - AR COLLECTIONS VERIFICATION")
print("=" * 60)

print(f"\n📊 AR METRICS:")
print(f"  AR Opening:              ₱{s.accounts_receivable_opening:,.2f}")
print(f"  AR Closing:              ₱{s.accounts_receivable_closing:,.2f}")
print(f"  AR Change:               ₱{s.accounts_receivable_closing - s.accounts_receivable_opening:,.2f}")
print(f"  AR Collections:          ₱{s.ar_collections:,.2f}")

print(f"\n💰 CASH METRICS:")
print(f"  Cash from Customers:     ₱{s.cash_from_customers:,.2f}")
print(f"  Cash Opening:            ₱{s.cash_opening:,.2f}")
print(f"  Cash Closing:            ₱{s.cash_closing:,.2f}")
print(f"  Cash Change:             ₱{s.cash_closing - s.cash_opening:,.2f}")

print(f"\n📦 INVENTORY METRICS:")
print(f"  Inventory Opening:       ₱{s.inventory_value_opening:,.2f}")
print(f"  Inventory Closing:       ₱{s.inventory_value_closing:,.2f}")
print(f"  Inventory Change:        ₱{s.inventory_value_closing - s.inventory_value_opening:,.2f}")
print(f"  Inventory Purchased:     ₱{s.inventory_purchased:,.2f}")
print(f"  COGS (Sold):             ₱{s.cogs_actual:,.2f}")

print(f"\n💼 TOTAL ASSETS:")
print(f"  Opening Balance:         ₱{s.opening_balance:,.2f}")
print(f"  Closing Balance:         ₱{s.closing_balance:,.2f}")
print(f"  Total Asset Change:      ₱{s.closing_balance - s.opening_balance:,.2f}")

print(f"\n✅ VERIFICATION:")
opening_calc = s.cash_opening + s.inventory_value_opening + s.accounts_receivable_opening
closing_calc = s.cash_closing + s.inventory_value_closing + s.accounts_receivable_closing
print(f"  Opening (Calculated):    ₱{opening_calc:,.2f}")
print(f"  Opening (Stored):        ₱{s.opening_balance:,.2f}")
print(f"  Match: {'✅' if abs(opening_calc - s.opening_balance) < 0.01 else '❌'}")
print(f"")
print(f"  Closing (Calculated):    ₱{closing_calc:,.2f}")
print(f"  Closing (Stored):        ₱{s.closing_balance:,.2f}")
print(f"  Match: {'✅' if abs(closing_calc - s.closing_balance) < 0.01 else '❌'}")

print("\n" + "=" * 60)
