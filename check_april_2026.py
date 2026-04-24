#!/usr/bin/env python
"""Quick script to check April 2026 cashflow data."""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'inventory_system.settings')
django.setup()

from cashflow.models import MonthlyCashflowSummary

# Get April 2026 summary
summary = MonthlyCashflowSummary.objects.filter(year=2026, month=4).first()

if summary:
    print("=" * 60)
    print("APRIL 2026 CASHFLOW SUMMARY")
    print("=" * 60)
    print(f"\n📊 REVENUE:")
    print(f"  Capital Sales:           ₱{summary.capital_sales:,.2f}")
    print(f"  Capital Other:           ₱{summary.capital_other:,.2f}")
    print(f"  Total Capital:           ₱{summary.capital_total:,.2f}")
    
    print(f"\n💸 EXPENSES:")
    print(f"  COGS (Actual):           ₱{summary.cogs_actual:,.2f}")
    print(f"  Procurement (Asset):     ₱{summary.expenses_procurement:,.2f}")
    print(f"  Operational:             ₱{summary.expenses_operational:,.2f}")
    print(f"  Other:                   ₱{summary.expenses_other:,.2f}")
    print(f"  Total Expenses:          ₱{summary.expenses_total:,.2f}")
    
    print(f"\n📈 PROFITABILITY:")
    print(f"  Gross Profit:            ₱{summary.capital_sales - summary.cogs_actual:,.2f}")
    print(f"  Net Profit:              ₱{summary.net_profit:,.2f}")
    print(f"  Profit Margin:           {summary.profit_margin:.2f}%")
    
    print(f"\n💰 BALANCE:")
    print(f"  Opening Balance:         ₱{summary.opening_balance:,.2f}")
    print(f"  Net Cash Flow:           ₱{summary.net_cash_flow:,.2f}")
    print(f"  Closing Balance:         ₱{summary.closing_balance:,.2f}")
    
    print(f"\n🔍 VERIFICATION:")
    print(f"  Expenses Total Formula:  COGS + Operational + Other")
    print(f"  Calculated:              ₱{summary.cogs_actual + summary.expenses_operational + summary.expenses_other:,.2f}")
    print(f"  Stored:                  ₱{summary.expenses_total:,.2f}")
    print(f"  Match:                   {'✅ YES' if abs(summary.expenses_total - (summary.cogs_actual + summary.expenses_operational + summary.expenses_other)) < 0.01 else '❌ NO'}")
    
    print(f"\n📦 INVENTORY:")
    print(f"  Opening Inventory:       ₱{summary.inventory_value_opening:,.2f}")
    print(f"  Purchased:               ₱{summary.inventory_purchased:,.2f}")
    print(f"  COGS (Sold):             ₱{summary.cogs_actual:,.2f}")
    print(f"  Closing Inventory:       ₱{summary.inventory_value_closing:,.2f}")
    
    print(f"\n🧮 INVENTORY VERIFICATION:")
    expected_closing = summary.inventory_value_opening + summary.inventory_purchased - summary.cogs_actual
    print(f"  Expected Closing:        ₱{expected_closing:,.2f}")
    print(f"  Actual Closing:          ₱{summary.inventory_value_closing:,.2f}")
    print(f"  Difference:              ₱{summary.inventory_value_closing - expected_closing:,.2f}")
    
    print("\n" + "=" * 60)
    print("CONCLUSION:")
    print("=" * 60)
    if summary.net_profit >= 0:
        print(f"✅ You made a PROFIT of ₱{summary.net_profit:,.2f}")
    else:
        print(f"❌ You had a LOSS of ₱{abs(summary.net_profit):,.2f}")
    
    print(f"\n⚠️  NOTE:")
    print(f"  - Procurement (₱{summary.expenses_procurement:,.2f}) is NOT an expense")
    print(f"  - It's an asset conversion (Cash → Inventory)")
    print(f"  - The actual expense is COGS (₱{summary.cogs_actual:,.2f})")
    print(f"  - COGS = Cost of inventory actually SOLD")
    print("=" * 60)
else:
    print("❌ No data found for April 2026")
