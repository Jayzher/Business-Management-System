"""
Diagnose the "Ghost 14 Million" Inventory Bug
==============================================
Identifies why inventory is being over-reported by ₱13.7M
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'inventory_system.settings')
django.setup()

from decimal import Decimal
from datetime import date
from cashflow.models import MonthlyCashflowSummary
from inventory.models import StockMove, MoveStatus, MoveType
from catalog.models import Item
from django.db.models import Sum
from django.db.models.functions import Coalesce

print('\n' + '='*80)
print('  GHOST INVENTORY DIAGNOSTIC')
print('='*80 + '\n')

# Get April 2026 summary
try:
    april = MonthlyCashflowSummary.objects.get(year=2026, month=4)
except MonthlyCashflowSummary.DoesNotExist:
    print('❌ April 2026 summary not found. Run calculate_financial_statements first.')
    exit(1)

print('APRIL 2026 REPORTED VALUES:')
print('-' * 80)
print(f'Opening Inventory:  ₱{april.inventory_value_opening:>15,.2f}')
print(f'Purchased:          ₱{april.inventory_purchased:>15,.2f}')
print(f'COGS (Sold):        ₱{april.cogs_actual:>15,.2f}')
print(f'Closing Inventory:  ₱{april.inventory_value_closing:>15,.2f}')

# Calculate expected
expected_closing = april.inventory_value_opening + april.inventory_purchased - april.cogs_actual
ghost_amount = april.inventory_value_closing - expected_closing

print(f'\nEXPECTED vs ACTUAL:')
print('-' * 80)
print(f'Expected Closing:   ₱{expected_closing:>15,.2f}')
print(f'Actual Closing:     ₱{april.inventory_value_closing:>15,.2f}')
print(f'GHOST AMOUNT:       ₱{ghost_amount:>15,.2f}  {"❌ BUG!" if abs(ghost_amount) > 100 else "✅ OK"}')

# Analyze stock moves
print(f'\n\nSTOCK MOVE ANALYSIS (April 2026):')
print('-' * 80)

april_start = date(2026, 4, 1)
april_end = date(2026, 5, 1)

for move_type in MoveType:
    moves = StockMove.objects.filter(
        status=MoveStatus.POSTED,
        posted_at__gte=april_start,
        posted_at__lt=april_end,
        move_type=move_type
    )
    if moves.exists():
        count = moves.count()
        total_qty = moves.aggregate(total=Coalesce(Sum('qty'), Decimal('0')))['total']
        print(f'{move_type.label:20s}: {count:4d} moves, Total Qty: {total_qty:>12,.2f}')

# Check for duplicate GRNs
print(f'\n\nDUPLICATE GRN CHECK:')
print('-' * 80)

from procurement.models import GoodsReceipt
from core.models import DocumentStatus

grns = GoodsReceipt.objects.filter(
    status=DocumentStatus.POSTED,
    receipt_date__gte=april_start,
    receipt_date__lt=april_end
)

print(f'Total GRNs in April: {grns.count()}')

# Check if any GRN created multiple RECEIVE moves
for grn in grns:
    receive_moves = StockMove.objects.filter(
        reference_type='GoodsReceipt',
        reference_id=grn.id,
        move_type=MoveType.RECEIVE,
        status=MoveStatus.POSTED
    )
    
    grn_lines = grn.lines.count()
    if receive_moves.count() != grn_lines:
        print(f'⚠️  {grn.document_number}: {grn_lines} lines but {receive_moves.count()} moves')

# Check for TRANSFER double-counting
print(f'\n\nTRANSFER MOVE ANALYSIS:')
print('-' * 80)

transfers = StockMove.objects.filter(
    status=MoveStatus.POSTED,
    posted_at__lt=april_end,
    move_type=MoveType.TRANSFER
)

if transfers.exists():
    total_transfer_qty = transfers.aggregate(total=Coalesce(Sum('qty'), Decimal('0')))['total']
    print(f'Total TRANSFER moves: {transfers.count()}')
    print(f'Total TRANSFER qty:   {total_transfer_qty:,.2f}')
    print(f'\n⚠️  WARNING: TRANSFER moves may be inflating inventory!')
    print(f'   Transfers are internal movements and should NOT add to total inventory.')
    print(f'   If counted as RECEIVE, they artificially inflate inventory value.')
else:
    print('✅ No TRANSFER moves found')

# Recalculate inventory manually
print(f'\n\nMANUAL INVENTORY CALCULATION (as of April 30, 2026):')
print('-' * 80)

from datetime import datetime, time
as_of = datetime.combine(date(2026, 4, 30), time.max)

total_inventory = Decimal('0')
items_with_moves = StockMove.objects.filter(
    status=MoveStatus.POSTED,
    posted_at__lte=as_of
).values_list('item_id', flat=True).distinct()

print(f'Items with movements: {len(set(items_with_moves))}')

for item_id in set(items_with_moves):
    try:
        item = Item.objects.get(id=item_id)
        cost = item.cost_price or Decimal('0')
        
        if cost == 0:
            continue
        
        # Count receives (excluding TRANSFER)
        receives = StockMove.objects.filter(
            item_id=item_id,
            status=MoveStatus.POSTED,
            posted_at__lte=as_of,
            move_type__in=[MoveType.RECEIVE, MoveType.RETURN_IN]
        ).aggregate(total=Coalesce(Sum('qty'), Decimal('0')))['total']
        
        # Count delivers
        delivers = StockMove.objects.filter(
            item_id=item_id,
            status=MoveStatus.POSTED,
            posted_at__lte=as_of,
            move_type__in=[MoveType.DELIVER, MoveType.POS_SALE, MoveType.SUPPLY_OUT, 
                           MoveType.SERVICE_OUT, MoveType.DAMAGE, MoveType.RETURN_OUT]
        ).aggregate(total=Coalesce(Sum('qty'), Decimal('0')))['total']
        
        # Count adjustments
        adjustments = StockMove.objects.filter(
            item_id=item_id,
            status=MoveStatus.POSTED,
            posted_at__lte=as_of,
            move_type=MoveType.ADJUST
        ).aggregate(total=Coalesce(Sum('qty'), Decimal('0')))['total']
        
        net_qty = receives - delivers + adjustments
        
        if net_qty > 0:
            item_value = net_qty * cost
            total_inventory += item_value
            
    except Item.DoesNotExist:
        continue

print(f'\nManual Calculation Result: ₱{total_inventory:,.2f}')
print(f'System Reported:           ₱{april.inventory_value_closing:,.2f}')
print(f'Difference:                ₱{april.inventory_value_closing - total_inventory:,.2f}')

if abs(april.inventory_value_closing - total_inventory) > 100:
    print(f'\n❌ CONFIRMED: Inventory calculation bug detected!')
    print(f'   The system is over-reporting by ₱{april.inventory_value_closing - total_inventory:,.2f}')
else:
    print(f'\n✅ Inventory calculation appears correct')

# Check historical accumulation
print(f'\n\nHISTORICAL INVENTORY TREND:')
print('-' * 80)

summaries = MonthlyCashflowSummary.objects.filter(year=2026).order_by('month')
for s in summaries:
    month_name = ['', 'Jan', 'Feb', 'Mar', 'Apr'][s.month] if s.month <= 4 else f'M{s.month}'
    expected = s.inventory_value_opening + s.inventory_purchased - s.cogs_actual
    diff = s.inventory_value_closing - expected
    status = '❌' if abs(diff) > 100 else '✅'
    print(f'{month_name} {s.year}: Opening ₱{s.inventory_value_opening:>12,.2f} + Purchased ₱{s.inventory_purchased:>12,.2f} - COGS ₱{s.cogs_actual:>12,.2f} = Expected ₱{expected:>12,.2f}, Actual ₱{s.inventory_value_closing:>12,.2f} {status}')

print('\n' + '='*80)
print('DIAGNOSIS COMPLETE')
print('='*80)
print('\nRECOMMENDED ACTIONS:')
print('1. Remove TRANSFER from inventory calculation (already fixed in code)')
print('2. Check for duplicate GRN processing')
print('3. Recalculate: python manage.py calculate_financial_statements --year 2026')
print('4. Verify: python verify_fixes.py')
print('\n')
