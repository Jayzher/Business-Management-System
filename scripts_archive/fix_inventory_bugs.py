"""
Comprehensive Inventory & Financial Bug Fix Script
===================================================
Addresses all 6 critical bugs identified in the system:
1. Vanishing Asset Bug - Inventory not tracked in assets
2. Negative Total Assets - Incorrect asset calculation
3. Frozen Liquidity Ratio - Cash not properly tracked
4. Contradictory Inventory Data - Sync issues
5. Net Profit Margin Miscalculation - Wrong formula
6. Zero-Value Procurements - Missing GRN values

Usage:
    python fix_inventory_bugs.py --diagnose
    python fix_inventory_bugs.py --fix-all
    python fix_inventory_bugs.py --fix-grns
    python fix_inventory_bugs.py --recalculate
"""
import os
import sys
import django
from decimal import Decimal

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'business_management.settings')
django.setup()

from django.core.management import call_command
from django.db import transaction
from cashflow.models import MonthlyCashflowSummary
from procurement.models import GoodsReceipt
from core.models import DocumentStatus


def print_header(title):
    print(f'\n{"="*80}')
    print(f'  {title}')
    print(f'{"="*80}\n')


def diagnose_bugs():
    """Run comprehensive diagnostics on all identified bugs."""
    print_header('COMPREHENSIVE BUG DIAGNOSIS')
    
    # Get data for Jan-Apr 2026
    summaries = MonthlyCashflowSummary.objects.filter(
        year=2026, month__in=[1, 2, 3, 4]
    ).order_by('month')
    
    if not summaries.exists():
        print('❌ No data found for 2026. Please run calculate_financial_statements first.')
        return
    
    print('\n1️⃣  BUG #1: VANISHING ASSET (Inventory Not in Assets)')
    print('-' * 80)
    for s in summaries:
        month_name = ['', 'Jan', 'Feb', 'Mar', 'Apr'][s.month]
        print(f'\n{month_name} 2026:')
        print(f'  Inventory Purchased:     ₱{s.inventory_purchased:>15,.2f}')
        print(f'  Inventory Opening:       ₱{s.inventory_value_opening:>15,.2f}')
        print(f'  Inventory Closing:       ₱{s.inventory_value_closing:>15,.2f}')
        print(f'  COGS (Sold):             ₱{s.cogs_actual:>15,.2f}')
        
        expected_closing = s.inventory_value_opening + s.inventory_purchased - s.cogs_actual
        diff = s.inventory_value_closing - expected_closing
        
        if abs(diff) > 1:
            print(f'  ❌ Expected Closing:      ₱{expected_closing:>15,.2f}')
            print(f'  ❌ Difference:            ₱{diff:>15,.2f}')
        else:
            print(f'  ✓ Inventory calculation correct')
    
    print('\n\n2️⃣  BUG #2: NEGATIVE TOTAL ASSETS')
    print('-' * 80)
    for s in summaries:
        month_name = ['', 'Jan', 'Feb', 'Mar', 'Apr'][s.month]
        total_assets = s.cash_closing + s.inventory_value_closing + s.accounts_receivable_closing
        
        print(f'\n{month_name} 2026:')
        print(f'  Cash:                    ₱{s.cash_closing:>15,.2f}')
        print(f'  Inventory:               ₱{s.inventory_value_closing:>15,.2f}')
        print(f'  Accounts Receivable:     ₱{s.accounts_receivable_closing:>15,.2f}')
        print(f'  Total Assets:            ₱{total_assets:>15,.2f}')
        print(f'  Stored Closing Balance:  ₱{s.closing_balance:>15,.2f}')
        
        if total_assets < 0:
            print(f'  ❌ NEGATIVE ASSETS!')
        elif abs(total_assets - s.closing_balance) > 1:
            print(f'  ⚠️  Mismatch: ₱{total_assets - s.closing_balance:>15,.2f}')
        else:
            print(f'  ✓ Assets calculated correctly')
    
    print('\n\n3️⃣  BUG #3: FROZEN LIQUIDITY RATIO')
    print('-' * 80)
    for s in summaries:
        month_name = ['', 'Jan', 'Feb', 'Mar', 'Apr'][s.month]
        liquidity = (s.cash_closing / s.closing_balance * 100) if s.closing_balance > 0 else 0
        
        print(f'\n{month_name} 2026:')
        print(f'  Cash:                    ₱{s.cash_closing:>15,.2f}')
        print(f'  Total Assets:            ₱{s.closing_balance:>15,.2f}')
        print(f'  Liquidity Ratio:         {liquidity:>15.2f}%')
        
        if s.cash_closing == 0 and s.cash_from_customers > 0:
            print(f'  ❌ Cash frozen despite ₱{s.cash_from_customers:,.2f} collected!')
    
    print('\n\n4️⃣  BUG #4: CONTRADICTORY INVENTORY DATA')
    print('-' * 80)
    for s in summaries:
        month_name = ['', 'Jan', 'Feb', 'Mar', 'Apr'][s.month]
        
        print(f'\n{month_name} 2026:')
        print(f'  Inventory Purchased:     ₱{s.inventory_purchased:>15,.2f}')
        print(f'  COGS (Sold):             ₱{s.cogs_actual:>15,.2f}')
        
        if s.inventory_purchased == 0 and s.cogs_actual > 0:
            print(f'  ❌ CONTRADICTION: Sold ₱{s.cogs_actual:,.2f} but purchased ₱0!')
    
    print('\n\n5️⃣  BUG #5: NET PROFIT MARGIN MISCALCULATION')
    print('-' * 80)
    for s in summaries:
        month_name = ['', 'Jan', 'Feb', 'Mar', 'Apr'][s.month]
        
        # Correct calculation
        correct_net_profit = s.revenue_accrual - s.cogs_actual - s.expenses_operational - s.expenses_other
        correct_margin = (correct_net_profit / s.revenue_accrual * 100) if s.revenue_accrual > 0 else 0
        
        # What system might be calculating wrong
        wrong_net_profit = s.revenue_accrual - s.inventory_purchased - s.expenses_operational - s.expenses_other
        wrong_margin = (wrong_net_profit / s.revenue_accrual * 100) if s.revenue_accrual > 0 else 0
        
        print(f'\n{month_name} 2026:')
        print(f'  Revenue:                 ₱{s.revenue_accrual:>15,.2f}')
        print(f'  COGS:                    ₱{s.cogs_actual:>15,.2f}')
        print(f'  Inventory Purchased:     ₱{s.inventory_purchased:>15,.2f}')
        print(f'  Operating Expenses:      ₱{s.expenses_operational:>15,.2f}')
        print(f'  Other Expenses:          ₱{s.expenses_other:>15,.2f}')
        print(f'  ')
        print(f'  ✓ Correct Net Profit:    ₱{correct_net_profit:>15,.2f} ({correct_margin:.1f}%)')
        print(f'  ❌ Wrong Net Profit:      ₱{wrong_net_profit:>15,.2f} ({wrong_margin:.1f}%)')
        print(f'  Stored Net Profit:       ₱{s.net_profit:>15,.2f}')
        
        if abs(s.net_profit - correct_net_profit) > 1:
            print(f'  ⚠️  System using wrong calculation!')
    
    print('\n\n6️⃣  BUG #6: ZERO-VALUE PROCUREMENTS')
    print('-' * 80)
    
    zero_grns = []
    grns = GoodsReceipt.objects.filter(
        status=DocumentStatus.POSTED,
        receipt_date__year=2026
    ).prefetch_related('lines__item', 'purchase_order__lines')
    
    for grn in grns:
        grn_total = Decimal('0')
        has_zero_lines = False
        
        for line in grn.lines.all():
            line_cost = Decimal('0')
            if grn.purchase_order:
                po_line = grn.purchase_order.lines.filter(item=line.item).first()
                if po_line:
                    line_cost = line.qty * po_line.unit_price
            
            if line_cost == 0 and line.qty > 0:
                has_zero_lines = True
            
            grn_total += line_cost
        
        if has_zero_lines:
            zero_grns.append((grn, grn_total))
    
    if zero_grns:
        print(f'\n❌ Found {len(zero_grns)} GRN(s) with zero-value lines:')
        for grn, total in zero_grns:
            print(f'  {grn.document_number} - {grn.receipt_date} - Total: ₱{total:,.2f}')
    else:
        print('\n✓ No zero-value GRNs found')
    
    print('\n\n' + '='*80)
    print('DIAGNOSIS COMPLETE')
    print('='*80)
    print('\nTo fix these issues, run:')
    print('  python fix_inventory_bugs.py --fix-all')


def fix_zero_grns():
    """Fix zero-value GRNs."""
    print_header('FIXING ZERO-VALUE GRNs')
    call_command('fix_zero_value_grns', '--fix', '--year', 2026)


def recalculate_financials():
    """Recalculate all financial statements."""
    print_header('RECALCULATING FINANCIAL STATEMENTS')
    call_command('calculate_financial_statements', '--year', 2026)


def fix_all():
    """Run all fixes."""
    print_header('COMPREHENSIVE FIX - ALL BUGS')
    
    print('\nStep 1: Fixing zero-value GRNs...')
    fix_zero_grns()
    
    print('\n\nStep 2: Recalculating financial statements with corrected inventory tracking...')
    recalculate_financials()
    
    print('\n\nStep 3: Running final verification...')
    diagnose_bugs()
    
    print_header('ALL FIXES COMPLETE')


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Fix inventory and financial bugs')
    parser.add_argument('--diagnose', action='store_true', help='Run diagnostics only')
    parser.add_argument('--fix-grns', action='store_true', help='Fix zero-value GRNs')
    parser.add_argument('--recalculate', action='store_true', help='Recalculate financial statements')
    parser.add_argument('--fix-all', action='store_true', help='Run all fixes')
    
    args = parser.parse_args()
    
    if args.diagnose:
        diagnose_bugs()
    elif args.fix_grns:
        fix_zero_grns()
    elif args.recalculate:
        recalculate_financials()
    elif args.fix_all:
        fix_all()
    else:
        print('Please specify an action: --diagnose, --fix-grns, --recalculate, or --fix-all')
        parser.print_help()
