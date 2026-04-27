#!/usr/bin/env python
"""Analyze the 4 discrepancies reported by the user."""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'inventory_system.settings')
django.setup()

from cashflow.models import MonthlyCashflowSummary
from decimal import Decimal

s = MonthlyCashflowSummary.objects.get(year=2026, month=4)

print("\n" + "=" * 70)
print("DISCREPANCY ANALYSIS - APRIL 2026")
print("=" * 70)

print("\n1️⃣  INVENTORY CALCULATION CHECK")
print("-" * 70)
print(f"Opening Inventory:       ₱{s.inventory_value_opening:,.2f}")
print(f"Purchased:               +₱{s.inventory_purchased:,.2f}")
print(f"Sold (COGS):             -₱{s.cogs_actual:,.2f}")
print(f"")
expected_closing = s.inventory_value_opening + s.inventory_purchased - s.cogs_actual
print(f"Expected Closing:        ₱{expected_closing:,.2f}")
print(f"Actual Closing:          ₱{s.inventory_value_closing:,.2f}")
print(f"Difference:              ₱{s.inventory_value_closing - expected_closing:,.2f}")
if abs(s.inventory_value_closing - expected_closing) > 1:
    print("❌ ISSUE: Inventory closing doesn't match formula!")
else:
    print("✅ OK: Inventory closing matches formula")

print("\n2️⃣  TOTAL ASSET CHANGE CHECK")
print("-" * 70)
print(f"Opening Balance:         ₱{s.opening_balance:,.2f}")
print(f"Closing Balance:         ₱{s.closing_balance:,.2f}")
print(f"")
actual_change = s.closing_balance - s.opening_balance
print(f"Actual Change:           ₱{actual_change:,.2f}")
print(f"")
# Check if template might be adding instead of subtracting
wrong_calc = s.closing_balance + s.opening_balance
print(f"If template ADDS:        ₱{wrong_calc:,.2f} ❌")
print(f"")
if abs(actual_change - Decimal('222726.06')) < 1:
    print("✅ OK: Backend calculates correct asset change")
else:
    print(f"❌ ISSUE: Asset change should be ₱222,726.06, got ₱{actual_change:,.2f}")

print("\n3️⃣  AR COLLECTIONS vs REVENUE CHECK")
print("-" * 70)
print(f"AR Opening:              ₱{s.accounts_receivable_opening:,.2f}")
print(f"AR Closing:              ₱{s.accounts_receivable_closing:,.2f}")
print(f"AR Collections:          ₱{s.ar_collections:,.2f}")
print(f"Cash from Customers:     ₱{s.cash_from_customers:,.2f}")
print(f"Sales Revenue:           ₱{s.capital_sales:,.2f}")
print(f"")
if s.ar_collections == s.cash_from_customers:
    print("⚠️  AR Collections = Cash from Customers (includes POS sales)")
if s.ar_collections == s.capital_sales:
    print("❌ ISSUE: AR Collections = Sales Revenue (WRONG!)")
else:
    print("✅ OK: AR Collections ≠ Sales Revenue")

print("\n4️⃣  NET CASH FLOW RECONCILIATION CHECK")
print("-" * 70)
print(f"Total Inflow:            ₱{s.total_inflow:,.2f}")
print(f"Total Outflow:           ₱{s.total_outflow:,.2f}")
print(f"")
calculated_net = s.total_inflow - s.total_outflow
print(f"Calculated Net:          ₱{calculated_net:,.2f}")
print(f"Reported Net Cash Flow:  ₱{s.net_cash_flow:,.2f}")
print(f"")
discrepancy = calculated_net - s.net_cash_flow
print(f"Discrepancy:             ₱{discrepancy:,.2f}")
print(f"")
if abs(discrepancy) > 1:
    print(f"❌ ISSUE: Net Cash Flow doesn't match Inflow - Outflow!")
    print(f"   Missing/Extra: ₱{discrepancy:,.2f}")
    print(f"")
    # Check if it matches cash change instead
    cash_change = s.cash_closing - s.cash_opening
    print(f"Cash Change (Closing - Opening): ₱{cash_change:,.2f}")
    if abs(s.net_cash_flow - cash_change) < 1:
        print(f"✅ Net Cash Flow matches Cash Change (correct for cash flow statement)")
else:
    print("✅ OK: Net Cash Flow matches Inflow - Outflow")

print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)

# Check each issue
issues = []

if abs(s.inventory_value_closing - expected_closing) > 1:
    issues.append("1. Inventory calculation")

if abs(actual_change - Decimal('222726.06')) > 1:
    issues.append("2. Asset change calculation")

if s.ar_collections == s.capital_sales:
    issues.append("3. AR Collections mislabeled")

if abs(discrepancy) > 1 and abs(s.net_cash_flow - cash_change) > 1:
    issues.append("4. Net Cash Flow reconciliation")

if issues:
    print(f"\n❌ Found {len(issues)} issue(s):")
    for issue in issues:
        print(f"   - {issue}")
else:
    print("\n✅ All calculations are correct!")
    print("\nNote: User may be seeing template display issues, not backend issues.")

print("\n" + "=" * 70)
