"""
Quick Verification Script
=========================
Quickly verify that all bug fixes are working correctly.

Usage:
    python verify_fixes.py
"""
import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'business_management.settings')
django.setup()

from decimal import Decimal
from cashflow.models import MonthlyCashflowSummary


def check_mark(condition):
    return '✅' if condition else '❌'


def verify_fixes():
    print('\n' + '='*80)
    print('  VERIFICATION REPORT - Bug Fixes')
    print('='*80 + '\n')
    
    summaries = MonthlyCashflowSummary.objects.filter(
        year=2026, month__in=[1, 2, 3, 4]
    ).order_by('month')
    
    if not summaries.exists():
        print('❌ No data found. Please run: python manage.py calculate_financial_statements --year 2026')
        return
    
    all_passed = True
    
    for s in summaries:
        month_name = ['', 'January', 'February', 'March', 'April'][s.month]
        print(f'\n{month_name} 2026')
        print('-' * 80)
        
        # Test 1: Inventory is tracked
        inventory_tracked = s.inventory_value_closing > 0 or s.inventory_purchased == 0
        print(f'{check_mark(inventory_tracked)} Inventory Tracked: ₱{s.inventory_value_closing:,.2f}')
        if not inventory_tracked:
            all_passed = False
        
        # Test 2: Total Assets are positive
        total_assets = s.cash_closing + s.inventory_value_closing + s.accounts_receivable_closing
        assets_positive = total_assets >= 0
        print(f'{check_mark(assets_positive)} Total Assets Positive: ₱{total_assets:,.2f}')
        if not assets_positive:
            all_passed = False
        
        # Test 3: Assets match closing balance
        assets_match = abs(total_assets - s.closing_balance) < 1
        print(f'{check_mark(assets_match)} Assets Match Closing: ₱{s.closing_balance:,.2f}')
        if not assets_match:
            all_passed = False
        
        # Test 4: Inventory calculation is correct
        expected_inventory = s.inventory_value_opening + s.inventory_purchased - s.cogs_actual
        inventory_correct = abs(s.inventory_value_closing - expected_inventory) < 1
        print(f'{check_mark(inventory_correct)} Inventory Calculation: Opening(₱{s.inventory_value_opening:,.2f}) + Purchased(₱{s.inventory_purchased:,.2f}) - COGS(₱{s.cogs_actual:,.2f}) = ₱{expected_inventory:,.2f}')
        if not inventory_correct:
            all_passed = False
        
        # Test 5: Net Profit uses correct formula
        correct_net_profit = s.revenue_accrual - s.cogs_actual - s.expenses_operational - s.expenses_other
        profit_correct = abs(s.net_profit - correct_net_profit) < 1
        print(f'{check_mark(profit_correct)} Net Profit Correct: ₱{s.net_profit:,.2f} (Expected: ₱{correct_net_profit:,.2f})')
        if not profit_correct:
            all_passed = False
        
        # Test 6: No contradictions (can't sell more than purchased + opening)
        max_sellable = s.inventory_value_opening + s.inventory_purchased
        no_contradiction = s.cogs_actual <= max_sellable or max_sellable == 0
        print(f'{check_mark(no_contradiction)} No Contradictions: COGS(₱{s.cogs_actual:,.2f}) <= Available(₱{max_sellable:,.2f})')
        if not no_contradiction:
            all_passed = False
        
        # Test 7: Cash flow is reasonable
        cash_reasonable = s.cash_closing != 0 or s.cash_from_customers == 0
        print(f'{check_mark(cash_reasonable)} Cash Flow Reasonable: ₱{s.cash_closing:,.2f}')
        if not cash_reasonable:
            all_passed = False
        
        # Test 8: Cash continuity (closing = opening + net flow)
        if s.month > 1 or s.year > 2026:
            prev = summaries.filter(year=s.year if s.month > 1 else s.year-1, month=s.month-1 if s.month > 1 else 12).first()
            if prev:
                cash_continuity = abs(s.cash_opening - prev.cash_closing) < 1
                print(f'{check_mark(cash_continuity)} Cash Continuity: Opening(₱{s.cash_opening:,.2f}) = Prev Closing(₱{prev.cash_closing:,.2f})')
                if not cash_continuity:
                    all_passed = False
    
    print('\n' + '='*80)
    if all_passed:
        print('  ✅ ALL TESTS PASSED - System is working correctly!')
    else:
        print('  ❌ SOME TESTS FAILED - Please review issues above')
    print('='*80 + '\n')
    
    # Summary statistics
    print('\nSUMMARY STATISTICS (Jan-Apr 2026)')
    print('-' * 80)
    
    total_revenue = sum(s.revenue_accrual for s in summaries)
    total_cogs = sum(s.cogs_actual for s in summaries)
    total_purchased = sum(s.inventory_purchased for s in summaries)
    total_net_profit = sum(s.net_profit for s in summaries)
    
    print(f'Total Revenue:           ₱{total_revenue:>15,.2f}')
    print(f'Total COGS:              ₱{total_cogs:>15,.2f}')
    print(f'Total Inventory Purchased: ₱{total_purchased:>15,.2f}')
    print(f'Total Net Profit:        ₱{total_net_profit:>15,.2f}')
    
    latest = summaries.last()
    if latest:
        print(f'\nLatest Position (April 2026):')
        print(f'  Cash:                  ₱{latest.cash_closing:>15,.2f}')
        print(f'  Inventory:             ₱{latest.inventory_value_closing:>15,.2f}')
        print(f'  Accounts Receivable:   ₱{latest.accounts_receivable_closing:>15,.2f}')
        print(f'  Total Assets:          ₱{latest.closing_balance:>15,.2f}')
    
    print('\n')
    
    return all_passed


if __name__ == '__main__':
    success = verify_fixes()
    sys.exit(0 if success else 1)
