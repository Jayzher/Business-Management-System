#!/usr/bin/env python
"""
Stock Movement & Balance Data Integrity Audit
================================================
Identifies missing stocks: items that were consumed (sold, delivered,
transferred to supply, used in services) but have no corresponding
StockMove or have StockBalance drift from the move ledger.

Run:  python manage.py shell < audit_stock_integrity.py

Checks:
  1. StockBalance vs StockMove ledger drift
  2. POS Sales without stock deduction (stock_deducted=False)
  3. Posted Deliveries/Pickups without matching StockMoves
  4. Completed Services without matching StockMoves
  5. Posted ISTs without matching SupplyMovements
  6. Orphaned StockMoves (source document deleted)
  7. Duplicate StockMoves
  8. Items with stock but zero/null cost_price
  9. Unposted documents that should have been posted
  10. Service lines missing location assignments
  11. Inventory value breakdown
"""
import os, sys, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'inventory_system.settings')
try:
    django.setup()
except:
    pass

from decimal import Decimal
from collections import defaultdict
from django.db.models import Sum, Count, Q, F, Min, Max, Subquery, OuterRef
from django.db.models.functions import Coalesce
from django.utils import timezone

from catalog.models import Item, convert_to_base_unit
from inventory.models import (
    StockBalance, StockMove, MoveType, MoveStatus,
    StockTransfer, StockAdjustment, DamagedReport,
)
from procurement.models import GoodsReceipt, GoodsReceiptLine
from core.models import Invoice, DocumentStatus, SupplyMovement, SupplyItem
from pos.models import POSSale, SaleStatus, POSRefund, RefundStatus
from sales.models import DeliveryNote, SalesPickup, SalesReturn
from services.models import CustomerService, ServiceStatus
from cashflow.models import CashFlowTransaction

W = '\033[93m'
E = '\033[91m'
G = '\033[92m'
B = '\033[96m'
R = '\033[0m'
BOLD = '\033[1m'
DIM = '\033[2m'

issues = []
warnings_list = []
ok_count = 0
total_missing_value = Decimal('0')

def ok(msg):
    global ok_count
    ok_count += 1
    print(f"  {G}✓{R} {msg}")

def warn(msg):
    warnings_list.append(msg)
    print(f"  {W}⚠{R} {msg}")

def error(msg):
    issues.append(msg)
    print(f"  {E}✗{R} {msg}")

def info(msg):
    print(f"  {B}ℹ{R} {msg}")

def detail(msg):
    print(f"    {DIM}{msg}{R}")

def header(title):
    print(f"\n{BOLD}{'═'*70}")
    print(f"  {title}")
    print(f"{'═'*70}{R}")

def money(v):
    return f"₱{v:,.2f}" if v else "₱0.00"


print(f"\n{BOLD}Stock Movement & Balance Data Integrity Audit{R}")
print(f"{'─'*50}")
print(f"  Date: {timezone.now().strftime('%Y-%m-%d %H:%M')}")
print(f"  Database: default (SQLite)")


# ══════════════════════════════════════════════════════════════════════════
header("1. STOCKBALANCE vs STOCKMOVE LEDGER DRIFT")
# ══════════════════════════════════════════════════════════════════════════
# Recalculate what each (item, location) balance SHOULD be from POSTED moves

info("Recalculating expected balances from all POSTED StockMoves...")

# Inbound moves: to_location gets +qty
inbound = (
    StockMove.objects
    .filter(status=MoveStatus.POSTED, to_location__isnull=False)
    .values('item_id', 'to_location_id')
    .annotate(total_in=Sum('qty'))
)
# Outbound moves: from_location gets -qty
outbound = (
    StockMove.objects
    .filter(status=MoveStatus.POSTED, from_location__isnull=False)
    .values('item_id', 'from_location_id')
    .annotate(total_out=Sum('qty'))
)

expected = defaultdict(Decimal)
for row in inbound:
    key = (row['item_id'], row['to_location_id'])
    expected[key] += row['total_in']
for row in outbound:
    key = (row['item_id'], row['from_location_id'])
    expected[key] -= row['total_out']

# Compare with actual StockBalance
drift_count = 0
drift_items = []
total_drift_value = Decimal('0')

for bal in StockBalance.objects.select_related('item', 'location').all():
    key = (bal.item_id, bal.location_id)
    exp = expected.pop(key, Decimal('0'))
    diff = bal.qty_on_hand - exp
    if abs(diff) > Decimal('0.001'):
        drift_count += 1
        cost = bal.item.cost_price or Decimal('0')
        drift_value = diff * cost
        total_drift_value += drift_value
        drift_items.append((bal.item.code, bal.item.name, bal.location.code,
                           bal.qty_on_hand, exp, diff, drift_value))

# Check for expected balances with no StockBalance row
for (item_id, loc_id), exp_qty in expected.items():
    if abs(exp_qty) > Decimal('0.001'):
        try:
            item = Item.objects.get(pk=item_id)
            from warehouses.models import Location
            loc = Location.objects.get(pk=loc_id)
            cost = item.cost_price or Decimal('0')
            drift_value = -exp_qty * cost  # missing balance = negative drift
            drift_count += 1
            total_drift_value += drift_value
            drift_items.append((item.code, item.name, loc.code,
                               Decimal('0'), exp_qty, -exp_qty, drift_value))
        except:
            pass

if drift_count == 0:
    ok("All StockBalance records match the StockMove ledger exactly")
else:
    error(f"{drift_count} balance(s) DRIFT from StockMove ledger (total value: {money(total_drift_value)})")
    drift_items.sort(key=lambda x: abs(x[6]), reverse=True)
    for code, name, loc, actual, expected_qty, diff, val in drift_items[:20]:
        detail(f"{code} ({name[:30]}) @ {loc}: actual={actual}, expected={expected_qty}, "
               f"diff={diff:+.4f}, value={money(val)}")
    if drift_count > 20:
        detail(f"... and {drift_count - 20} more")


# ══════════════════════════════════════════════════════════════════════════
header("2. POS SALES WITHOUT STOCK DEDUCTION")
# ══════════════════════════════════════════════════════════════════════════

pos_no_deduct = POSSale.objects.filter(
    status__in=[SaleStatus.POSTED, SaleStatus.PAID],
    stock_deducted=False,
)
count = pos_no_deduct.count()
if count == 0:
    ok("All posted/paid POS sales have stock_deducted=True")
else:
    error(f"{count} POS sale(s) are POSTED/PAID but stock_deducted=False")
    for sale in pos_no_deduct.select_related('location')[:10]:
        total = sale.grand_total or Decimal('0')
        detail(f"{sale.sale_no} ({sale.created_at.date()}) total={money(total)} "
               f"location={sale.location}")
    if count > 10:
        detail(f"... and {count - 10} more")

# Also check for POS sales with no StockMoves at all
pos_posted = POSSale.objects.filter(status=SaleStatus.POSTED)
pos_with_moves = set(
    StockMove.objects.filter(
        reference_type='POSSale', status=MoveStatus.POSTED
    ).values_list('reference_id', flat=True).distinct()
)
pos_no_moves = pos_posted.exclude(pk__in=pos_with_moves)
count2 = pos_no_moves.count()
if count2 == 0:
    ok("All POSTED POS sales have corresponding StockMoves")
else:
    error(f"{count2} POSTED POS sale(s) have NO StockMoves at all")
    for sale in pos_no_moves[:5]:
        detail(f"{sale.sale_no} ({sale.created_at.date()}) total={money(sale.grand_total)}")


# ══════════════════════════════════════════════════════════════════════════
header("3. DELIVERIES & PICKUPS WITHOUT STOCK MOVES")
# ══════════════════════════════════════════════════════════════════════════

for label, Model, ref_type in [
    ('Delivery Notes', DeliveryNote, 'DeliveryNote'),
    ('Sales Pickups', SalesPickup, 'SalesPickup'),
]:
    posted_docs = Model.objects.filter(status=DocumentStatus.POSTED)
    docs_with_moves = set(
        StockMove.objects.filter(
            reference_type=ref_type, status=MoveStatus.POSTED
        ).values_list('reference_id', flat=True).distinct()
    )
    missing = posted_docs.exclude(pk__in=docs_with_moves)
    count = missing.count()
    if count == 0:
        ok(f"All POSTED {label} have corresponding StockMoves")
    else:
        error(f"{count} POSTED {label} have NO StockMoves")
        for doc in missing[:5]:
            detail(f"{doc.document_number} ({getattr(doc, 'created_at', 'N/A')})")


# ══════════════════════════════════════════════════════════════════════════
header("4. COMPLETED SERVICES WITHOUT STOCK MOVES")
# ══════════════════════════════════════════════════════════════════════════

completed_services = CustomerService.objects.filter(status=ServiceStatus.COMPLETED)
svc_with_moves = set(
    StockMove.objects.filter(
        reference_type='CustomerService', status=MoveStatus.POSTED
    ).values_list('reference_id', flat=True).distinct()
)

# Check which completed services have material lines but no moves
svc_missing_moves = []
for svc in completed_services.prefetch_related('lines').all():
    material_lines = [l for l in svc.lines.all() if not getattr(l, 'is_scrap', False)]
    if material_lines and svc.pk not in svc_with_moves:
        svc_missing_moves.append(svc)

if not svc_missing_moves:
    ok("All COMPLETED services with materials have StockMoves")
else:
    error(f"{len(svc_missing_moves)} COMPLETED service(s) with materials have NO StockMoves")
    for svc in svc_missing_moves[:5]:
        line_count = svc.lines.filter(is_scrap=False).count()
        detail(f"{svc.service_number} ({svc.service_date}) — {line_count} material line(s)")

# Check service lines without location
svc_lines_no_loc = 0
try:
    from services.models import ServiceLine
    svc_lines_no_loc = ServiceLine.objects.filter(
        service__status=ServiceStatus.COMPLETED,
        is_scrap=False,
        location__isnull=True,
    ).count()
except:
    pass

if svc_lines_no_loc == 0:
    ok("All completed service material lines have a location assigned")
else:
    warn(f"{svc_lines_no_loc} completed service material line(s) have NO location — stock NOT deducted")


# ══════════════════════════════════════════════════════════════════════════
header("5. INVENTORY-TO-SUPPLY TRANSFERS INTEGRITY")
# ══════════════════════════════════════════════════════════════════════════

try:
    from inventory.models import InventoryToSupplyTransfer
    posted_ists = InventoryToSupplyTransfer.objects.filter(status=DocumentStatus.POSTED)
    ist_with_moves = set(
        StockMove.objects.filter(
            reference_type='InventoryToSupplyTransfer', status=MoveStatus.POSTED
        ).values_list('reference_id', flat=True).distinct()
    )
    ist_missing = posted_ists.exclude(pk__in=ist_with_moves)
    count = ist_missing.count()
    if count == 0:
        ok("All POSTED ISTs have corresponding StockMoves")
    else:
        error(f"{count} POSTED IST(s) have NO StockMoves (inventory deducted but not tracked)")

    # Check for IST StockMoves without matching SupplyMovements
    ist_move_refs = (
        StockMove.objects.filter(
            reference_type='InventoryToSupplyTransfer',
            status=MoveStatus.POSTED,
        ).values_list('reference_number', flat=True).distinct()
    )
    supply_refs = set(
        SupplyMovement.objects.filter(
            movement_type='IN',
        ).values_list('reference', flat=True)
    )
    orphaned_ists = [ref for ref in ist_move_refs if ref and ref not in supply_refs]
    if not orphaned_ists:
        ok("All IST StockMoves have matching SupplyMovements")
    else:
        warn(f"{len(orphaned_ists)} IST(s) deducted inventory but SupplyMovement is missing")
        for ref in orphaned_ists[:5]:
            detail(f"IST {ref}: inventory deducted, supply NOT credited")
except ImportError:
    info("InventoryToSupplyTransfer model not found — skipping")


# ══════════════════════════════════════════════════════════════════════════
header("6. ORPHANED & DUPLICATE STOCK MOVES")
# ══════════════════════════════════════════════════════════════════════════

# Orphaned moves: reference document no longer exists
from procurement.models import PurchaseReturn
model_map = {
    'GoodsReceipt': GoodsReceipt,
    'DeliveryNote': DeliveryNote,
    'SalesPickup': SalesPickup,
    'StockTransfer': StockTransfer,
    'StockAdjustment': StockAdjustment,
    'DamagedReport': DamagedReport,
    'POSSale': POSSale,
    'POSRefund': POSRefund,
    'PurchaseReturn': PurchaseReturn,
    'SalesReturn': SalesReturn,
    'CustomerService': CustomerService,
}

try:
    from inventory.models import InventoryToSupplyTransfer
    model_map['InventoryToSupplyTransfer'] = InventoryToSupplyTransfer
except ImportError:
    pass

total_orphaned = 0
for ref_type, Model in model_map.items():
    move_ref_ids = set(
        StockMove.objects.filter(
            status=MoveStatus.POSTED, reference_type=ref_type
        ).exclude(reference_id__isnull=True)
        .values_list('reference_id', flat=True).distinct()
    )
    if not move_ref_ids:
        continue
    existing_ids = set(Model.objects.filter(pk__in=move_ref_ids).values_list('pk', flat=True))
    orphaned = move_ref_ids - existing_ids
    if orphaned:
        count = StockMove.objects.filter(
            status=MoveStatus.POSTED, reference_type=ref_type,
            reference_id__in=orphaned,
        ).count()
        total_orphaned += count
        warn(f"{count} orphaned StockMove(s) for {ref_type} (source document deleted)")

if total_orphaned == 0:
    ok("No orphaned StockMoves found")

# Duplicate moves
dupes = list(
    StockMove.objects
    .filter(status=MoveStatus.POSTED)
    .exclude(reference_number__startswith='REV-')
    .values('reference_type', 'reference_id', 'item_id',
            'from_location_id', 'to_location_id')
    .annotate(cnt=Count('id'))
    .filter(cnt__gt=1)
)
if not dupes:
    ok("No duplicate StockMoves found")
else:
    warn(f"{len(dupes)} duplicate StockMove group(s) found")
    for grp in dupes[:5]:
        detail(f"{grp['reference_type']}#{grp['reference_id']} item={grp['item_id']} "
               f"count={grp['cnt']}")


# ══════════════════════════════════════════════════════════════════════════
header("7. ITEMS WITH STOCK BUT ZERO/NULL COST PRICE")
# ══════════════════════════════════════════════════════════════════════════

items_with_stock = (
    Item.objects
    .filter(balances__qty_on_hand__gt=Decimal('0.001'))
    .distinct()
    .annotate(total_qty=Sum('balances__qty_on_hand'))
)

zero_cost = items_with_stock.filter(Q(cost_price=0) | Q(cost_price__isnull=True))
count = zero_cost.count()
if count == 0:
    ok("All items with stock have valid cost prices")
else:
    error(f"{count} item(s) with stock have ZERO or NULL cost price — inventory value understated")
    for item in zero_cost[:10]:
        detail(f"{item.code} ({item.name[:30]}): qty={item.total_qty:.2f}, cost=₱0")


# ══════════════════════════════════════════════════════════════════════════
header("8. UNPOSTED DOCUMENTS (STUCK IN DRAFT/APPROVED)")
# ══════════════════════════════════════════════════════════════════════════

cutoff = timezone.now() - timezone.timedelta(days=7)

for label, Model, status_field in [
    ('Goods Receipts', GoodsReceipt, 'status'),
    ('Delivery Notes', DeliveryNote, 'status'),
    ('Sales Pickups', SalesPickup, 'status'),
    ('Stock Transfers', StockTransfer, 'status'),
    ('Stock Adjustments', StockAdjustment, 'status'),
    ('Damaged Reports', DamagedReport, 'status'),
]:
    stuck = Model.objects.filter(
        **{status_field: DocumentStatus.DRAFT},
        created_at__lt=cutoff,
    )
    count = stuck.count()
    if count > 0:
        warn(f"{count} {label} stuck in DRAFT for >7 days (stock NOT affected)")
        for doc in stuck[:3]:
            detail(f"{doc.document_number} created {doc.created_at.date()}")

# Approved but not posted adjustments
approved_adj = StockAdjustment.objects.filter(
    status=DocumentStatus.APPROVED,
    created_at__lt=cutoff,
)
if approved_adj.exists():
    warn(f"{approved_adj.count()} Stock Adjustment(s) APPROVED but NOT POSTED for >7 days")


# ══════════════════════════════════════════════════════════════════════════
header("9. INVENTORY VALUE BREAKDOWN")
# ══════════════════════════════════════════════════════════════════════════

total_value = Decimal('0')
total_qty = Decimal('0')
value_by_type = defaultdict(Decimal)
qty_by_type = defaultdict(Decimal)
items_contributing = 0

for bal in StockBalance.objects.filter(
    qty_on_hand__gt=Decimal('0.001')
).select_related('item'):
    cost = bal.item.cost_price or Decimal('0')
    value = bal.qty_on_hand * cost
    total_value += value
    total_qty += bal.qty_on_hand
    item_type = bal.item.item_type if hasattr(bal.item, 'item_type') else 'UNKNOWN'
    value_by_type[item_type] += value
    qty_by_type[item_type] += bal.qty_on_hand
    if value > 0:
        items_contributing += 1

info(f"Total Inventory Value: {money(total_value)}")
info(f"Total Items with Stock: {items_contributing}")
info(f"Total Qty on Hand: {total_qty:,.2f}")
print()
for itype in sorted(value_by_type.keys()):
    info(f"  {itype}: {money(value_by_type[itype])} ({qty_by_type[itype]:,.2f} units)")


# ══════════════════════════════════════════════════════════════════════════
header("10. STOCK MOVE SUMMARY BY TYPE")
# ══════════════════════════════════════════════════════════════════════════

move_summary = (
    StockMove.objects
    .filter(status=MoveStatus.POSTED)
    .values('move_type')
    .annotate(
        count=Count('id'),
        total_qty=Sum('qty'),
    )
    .order_by('move_type')
)

for row in move_summary:
    info(f"  {row['move_type']:15s}: {row['count']:6d} moves, total qty={row['total_qty']:,.2f}")


# ══════════════════════════════════════════════════════════════════════════
header("11. MISSING STOCK ANALYSIS — WHERE DID STOCK GO?")
# ══════════════════════════════════════════════════════════════════════════

# Calculate total received vs total outbound
total_received = StockMove.objects.filter(
    status=MoveStatus.POSTED,
    move_type__in=[MoveType.RECEIVE, MoveType.RETURN_IN, MoveType.ADJUST],
    to_location__isnull=False,
).aggregate(total=Sum('qty'))['total'] or Decimal('0')

total_outbound = StockMove.objects.filter(
    status=MoveStatus.POSTED,
    move_type__in=[MoveType.DELIVER, MoveType.POS_SALE, MoveType.DAMAGE,
                   MoveType.RETURN_OUT, MoveType.SUPPLY_OUT, MoveType.SERVICE_OUT,
                   MoveType.ADJUST],
    from_location__isnull=False,
).aggregate(total=Sum('qty'))['total'] or Decimal('0')

# Transfers are zero-sum (in = out)
expected_on_hand = total_received - total_outbound
actual_on_hand = StockBalance.objects.aggregate(
    total=Sum('qty_on_hand')
)['total'] or Decimal('0')

info(f"Total Received (GRN + Returns + Adj-In): {total_received:,.2f}")
info(f"Total Outbound (Sales + Deliver + Damage + Supply + Service + Adj-Out): {total_outbound:,.2f}")
info(f"Expected On Hand (from moves): {expected_on_hand:,.2f}")
info(f"Actual On Hand (StockBalance): {actual_on_hand:,.2f}")
diff = actual_on_hand - expected_on_hand
if abs(diff) > Decimal('0.01'):
    error(f"DISCREPANCY: {diff:+,.2f} units between move ledger and balance table")
else:
    ok(f"Move ledger and balance table are in sync (diff={diff:+.4f})")


# ══════════════════════════════════════════════════════════════════════════
header("12. TOP ITEMS WITH NEGATIVE BALANCE")
# ══════════════════════════════════════════════════════════════════════════

negative_balances = StockBalance.objects.filter(
    qty_on_hand__lt=Decimal('0')
).select_related('item', 'location').order_by('qty_on_hand')

count = negative_balances.count()
if count == 0:
    ok("No negative stock balances found")
else:
    warn(f"{count} item/location pair(s) have NEGATIVE stock balance")
    total_neg_value = Decimal('0')
    for bal in negative_balances[:15]:
        cost = bal.item.cost_price or Decimal('0')
        val = bal.qty_on_hand * cost
        total_neg_value += val
        detail(f"{bal.item.code} @ {bal.location.code}: {bal.qty_on_hand:.4f} "
               f"(value: {money(val)})")
    if count > 15:
        detail(f"... and {count - 15} more")
    info(f"Total negative balance value: {money(total_neg_value)}")


# ══════════════════════════════════════════════════════════════════════════
header("SUMMARY")
# ══════════════════════════════════════════════════════════════════════════

print(f"\n  {G}✓ {ok_count} checks passed{R}")
if warnings_list:
    print(f"  {W}⚠ {len(warnings_list)} warning(s){R}")
if issues:
    print(f"  {E}✗ {len(issues)} issue(s) found{R}")
    print(f"\n  {BOLD}Issues requiring attention:{R}")
    for i, issue in enumerate(issues, 1):
        print(f"    {i}. {issue}")

print(f"\n  Inventory Value: {money(total_value)}")
if total_drift_value != 0:
    print(f"  Balance Drift Value: {money(total_drift_value)}")
print()
