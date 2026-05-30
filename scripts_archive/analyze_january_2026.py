#!/usr/bin/env python
"""Analyze January 2026 data for the reported issues."""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'inventory_system.settings')
django.setup()

from cashflow.models import MonthlyCashflowSummary, CashFlowTransaction, CashFlowType, CashFlowStatus
from datetime import date

try:
    s = MonthlyCashflowSummary.objects.get(year=2026, month=1)
    
    print("\n" + "=" * 70)
    print("JANUARY 2026 - ISSUE ANALYSIS")
    print("=" * 70)
    
    print("\n1️⃣  GHOST CASH PROBLEM")
    print("-" * 70)
    print(f"Total Inflow:            ₱{s.total_inflow:,.2f}")
    print(f"Total Outflow:           ₱{s.total_outflow:,.2f}")
    print(f"")
    print(f"Opening Balance:         ₱{s.opening_balance:,.2f}")
    print(f"Closing Balance:         ₱{s.closing_balance:,.2f}")
    print(f"")
    print(f"Cash Opening:            ₱{s.cash_opening:,.2f}")
    print(f"Cash Closing:            ₱{s.cash_closing:,.2f}")
    print(f"Cash from Customers:     ₱{s.cash_from_customers:,.2f}")
    print(f"")
    print(f"Inventory Opening:       ₱{s.inventory_value_opening:,.2f}")
    print(f"Inventory Closing:       ₱{s.inventory_value_closing:,.2f}")
    print(f"")
    print(f"AR Opening:              ₱{s.accounts_receivable_opening:,.2f}")
    print(f"AR Closing:              ₱{s.accounts_receivable_closing:,.2f}")
    print(f"")
    
    # Check if closing balance matches components
    closing_calc = s.cash_closing + s.inventory_value_closing + s.accounts_receivable_closing
    print(f"Closing (Calculated):    ₱{closing_calc:,.2f}")
    print(f"Closing (Stored):        ₱{s.closing_balance:,.2f}")
    
    if abs(closing_calc - s.closing_balance) > 0.01:
        print(f"❌ ISSUE: Components don't match total!")
        print(f"   Difference: ₱{s.closing_balance - closing_calc:,.2f}")
    else:
        print(f"✅ Components match total")
    
    print("\n2️⃣  CASH FLOW TRANSACTIONS CHECK")
    print("-" * 70)
    
    # Check for capital injections
    start_date = date(2026, 1, 1)
    end_date = date(2026, 2, 1)
    
    capital_txns = CashFlowTransaction.objects.filter(
        status=CashFlowStatus.APPROVED,
        flow_type=CashFlowType.CASH_IN,
        transaction_date__gte=start_date,
        transaction_date__lt=end_date,
    )
    
    if capital_txns.exists():
        print(f"Found {capital_txns.count()} cash-in transaction(s):")
        total_capital = 0
        for txn in capital_txns:
            print(f"  {txn.transaction_date} - {txn.get_category_display()} - ₱{txn.amount:,.2f}")
            total_capital += txn.amount
        print(f"\nTotal Capital In: ₱{total_capital:,.2f}")
    else:
        print("❌ NO cash-in transactions found")
    
    print("\n3️⃣  CAPITAL TRACKING")
    print("-" * 70)
    print(f"Capital (Sales):         ₱{s.capital_sales:,.2f}")
    print(f"Capital (Other):         ₱{s.capital_other:,.2f}")
    print(f"Capital (Total):         ₱{s.capital_total:,.2f}")
    
    print("\n4️⃣  BALANCE SHEET VERIFICATION")
    print("-" * 70)
    
    # Opening
    opening_calc = s.cash_opening + s.inventory_value_opening + s.accounts_receivable_opening
    print(f"Opening Components:")
    print(f"  Cash:                  ₱{s.cash_opening:,.2f}")
    print(f"  Inventory:             ₱{s.inventory_value_opening:,.2f}")
    print(f"  AR:                    ₱{s.accounts_receivable_opening:,.2f}")
    print(f"  Total (Calculated):    ₱{opening_calc:,.2f}")
    print(f"  Total (Stored):        ₱{s.opening_balance:,.2f}")
    
    if abs(opening_calc - s.opening_balance) > 0.01:
        print(f"❌ Opening doesn't match! Difference: ₱{s.opening_balance - opening_calc:,.2f}")
    else:
        print(f"✅ Opening matches")
    
    # Closing
    print(f"\nClosing Components:")
    print(f"  Cash:                  ₱{s.cash_closing:,.2f}")
    print(f"  Inventory:             ₱{s.inventory_value_closing:,.2f}")
    print(f"  AR:                    ₱{s.accounts_receivable_closing:,.2f}")
    print(f"  Total (Calculated):    ₱{closing_calc:,.2f}")
    print(f"  Total (Stored):        ₱{s.closing_balance:,.2f}")
    
    if abs(closing_calc - s.closing_balance) > 0.01:
        print(f"❌ Closing doesn't match! Difference: ₱{s.closing_balance - closing_calc:,.2f}")
    else:
        print(f"✅ Closing matches")
    
    print("\n5️⃣  DIAGNOSIS")
    print("-" * 70)
    
    issues = []
    
    # Check if cash is zero but closing balance is not
    if s.cash_closing == 0 and s.closing_balance > 0:
        issues.append("Cash closing is ₱0 but closing balance is positive")
        issues.append("Capital injections not being added to cash")
    
    # Check if components don't match total
    if abs(closing_calc - s.closing_balance) > 0.01:
        issues.append("Closing balance components don't sum to total")
    
    if issues:
        print("❌ ISSUES FOUND:")
        for i, issue in enumerate(issues, 1):
            print(f"   {i}. {issue}")
    else:
        print("✅ No issues found")
    
    print("\n" + "=" * 70)
    
except MonthlyCashflowSummary.DoesNotExist:
    print("\n❌ January 2026 data not found!")
    print("   Run: python manage.py calculate_monthly_cashflow --year 2026 --month 1")
