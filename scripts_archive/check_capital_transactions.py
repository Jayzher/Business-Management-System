"""
Check if capital transactions exist in the database
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'business_management.settings')
django.setup()

from cashflow.models import CashFlowTransaction, CashFlowCategory, CashFlowStatus, CashFlowType
from datetime import date
from decimal import Decimal

print('\n' + '='*80)
print('  CAPITAL TRANSACTIONS CHECK')
print('='*80 + '\n')

# Check for capital transactions
capital_txns = CashFlowTransaction.objects.filter(
    category=CashFlowCategory.CAPITAL,
    flow_type=CashFlowType.CASH_IN,
    transaction_date__year=2026
)

print(f'Total Capital Transactions (2026): {capital_txns.count()}')

if capital_txns.exists():
    print('\nCapital Transactions Found:')
    print('-' * 80)
    for txn in capital_txns:
        status_mark = '✅' if txn.status == CashFlowStatus.APPROVED else '⚠️'
        print(f'{status_mark} {txn.transaction_number}')
        print(f'   Date: {txn.transaction_date}')
        print(f'   Amount: ₱{txn.amount:,.2f}')
        print(f'   Status: {txn.get_status_display()}')
        print(f'   Reason: {txn.reason}')
        print()
    
    # Check approved only
    approved = capital_txns.filter(status=CashFlowStatus.APPROVED)
    total_approved = sum(t.amount for t in approved)
    print(f'Approved Capital Transactions: {approved.count()}')
    print(f'Total Approved Amount: ₱{total_approved:,.2f}')
else:
    print('\n❌ NO CAPITAL TRANSACTIONS FOUND!')
    print('\nTo create a capital transaction, use:')
    print("""
from cashflow.models import CashFlowTransaction, CashFlowCategory, CashFlowType, CashFlowStatus
from datetime import date
from decimal import Decimal

CashFlowTransaction.objects.create(
    transaction_number=CashFlowTransaction.generate_next_number(),
    category=CashFlowCategory.CAPITAL,
    flow_type=CashFlowType.CASH_IN,
    amount=Decimal('600000.00'),
    transaction_date=date(2026, 1, 15),
    reason='Owner capital injection',
    status=CashFlowStatus.APPROVED,
    created_by=user,
    approved_by=user,
    approved_at=timezone.now()
)
""")

print('\n' + '='*80)

# Check all cash in transactions
print('\nAll CASH_IN Transactions by Category (2026):')
print('-' * 80)

from django.db.models import Sum

for category in CashFlowCategory:
    txns = CashFlowTransaction.objects.filter(
        flow_type=CashFlowType.CASH_IN,
        category=category,
        status=CashFlowStatus.APPROVED,
        transaction_date__year=2026
    )
    if txns.exists():
        total = txns.aggregate(Sum('amount'))['amount__sum'] or Decimal('0')
        print(f'{category.label:20s}: {txns.count():3d} transactions, Total: ₱{total:>15,.2f}')

print('\n' + '='*80)
