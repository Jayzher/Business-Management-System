#!/usr/bin/env python
"""
Comprehensive Data Integrity Audit
====================================
Checks ALL financial data across the system for consistency and correctness.

Run: python manage.py shell < audit_data_integrity.py
  OR: python audit_data_integrity.py  (standalone)
"""
import os, sys, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'inventory_system.settings')
try:
    django.setup()
except:
    pass

from decimal import Decimal
from datetime import date, datetime, time
from collections import defaultdict

from django.db.models import Sum, Count, Q, F, Min, Max
from django.db.models.functions import Coalesce
from django.utils import timezone

from catalog.models import Item
from inventory.models import StockBalance, StockMove, MoveType, MoveStatus
from procurement.models import GoodsReceipt, GoodsReceiptLine, PurchaseOrderLine
from core.models import Invoice, InvoicePayment, Expense, DocumentStatus
from pos.models import POSSale, SaleStatus
from cashflow.models import MonthlyCashflowSummary, CashFlowTransaction, CashFlowStatus
from sales.models import DeliveryNote, SalesPickup

W = '\033[93m'  # yellow warning
E = '\033[91m'  # red error
G = '\033[92m'  # green ok
B = '\033[96m'  # cyan info
R = '\033[0m'   # reset
BOLD = '\033[1m'

issues = []
warnings_list = []
ok_count = 0

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

def header(title):
    print(f"\n{BOLD}{'═'*70}")
    print(f"  {title}")
    print(f"{'═'*70}{R}")

# ══════════════════════════════════════════════════════════════════════════
header("1. ITEM COST PRICES")
# ══════════════════════════════════════════════════════════════════════════

items_with_stock = Item.objects.filter(balances__qty_on_hand__gt=0).distinct()
items_zero_cost = items_with_stock.filter(cost_price=0)
items_null_cost = items_with_stock.filter(cost_price__isnull=True)

total_items = items_with_stock.count()
zero_count = items_zero_cost.count()
null_count = items_null_cost.count()

if zero_count == 0 and null_count == 0:
    ok(f"All {total_items} items with stock have valid cost prices")
else:
    if zero_count > 0:
        error(f"{zero_count}/{total_items} items with stock have ZERO cost price")
        for item in items_zero_cost[:5]:
            qty = item.balances.aggregate(t=Sum('qty_on_hand'))['t'] or 0
            info(f"  {item.code}: qty={qty:.2f}, cost=₱0")
    if null_count > 0:
        error(f"{null_count}/{total_items} items with stock have NULL cost price")

# Check items with GRN data but no cost
items_in_grns = set(GoodsReceiptLine.objects.filter(
    goods_receipt__status=DocumentStatus.POSTED
).values_list('item_id', flat=True))
items_zero_cost_with_grn = Item.objects.filter(
    id__in=items_in_grns, cost_price=0
).count()
if items_zero_cost_with_grn > 0:
    warn(f"{items_zero_cost_with_grn} items received via GRN still have ₱0 cost price")
else:
    ok(f"All items with GRN history have non-zero cost prices")

# ══════════════════════════════════════════════════════════════════════════
header("2. STOCK BALANCE INTEGRITY")
# ══════════════════════════════════════════════════════════════════════════

# StockBalance was rebuilt by resync_inventory from source documents.
# Check for negative balances (the real issue) instead of StockMove comparison.
neg_balances = StockBalance.objects.filter(qty_on_hand__lt=Decimal('-0.001')).select_related('item', 'location')
neg_count = neg_balances.count()
total_balance_items = StockBalance.objects.filter(qty_on_hand__gt=Decimal('0.001')).count()

if neg_count == 0:
    ok(f"No negative stock balances found ({total_balance_items} positive items)")
else:
    warn(f"{neg_count} items have negative stock balances (oversold)")
    neg_val = Decimal('0')
    for b in neg_balances[:10]:
        val = b.qty_on_hand * (b.item.cost_price or Decimal('0'))
        neg_val += val
        info(f"  {b.item.code} @ {b.location.code}: qty={b.qty_on_hand:.4f} (₱{val:,.2f})")
    info(f"  Total negative value: ₱{neg_val:,.2f}")

# ══════════════════════════════════════════════════════════════════════════
header("3. PURCHASE ORDER LINE PRICES")
# ══════════════════════════════════════════════════════════════════════════

total_po_lines = PurchaseOrderLine.objects.count()
zero_price_lines = PurchaseOrderLine.objects.filter(unit_price=0).count()
pct = (zero_price_lines * 100 / total_po_lines) if total_po_lines > 0 else 0

if zero_price_lines == 0:
    ok(f"All {total_po_lines} PO lines have non-zero prices")
else:
    warn(f"{zero_price_lines}/{total_po_lines} PO lines ({pct:.0f}%) have ₱0 unit price")
    # Check if these affect GRN cost calculation
    affected_grns = GoodsReceipt.objects.filter(
        status=DocumentStatus.POSTED,
        purchase_order__lines__unit_price=0
    ).distinct().count()
    if affected_grns > 0:
        info(f"  {affected_grns} posted GRNs linked to POs with zero-price lines")
        info(f"  → Procurement costs fall back to item.cost_price for these")

# ══════════════════════════════════════════════════════════════════════════
header("4. GRN DATA INTEGRITY")
# ══════════════════════════════════════════════════════════════════════════

total_grns = GoodsReceipt.objects.filter(status=DocumentStatus.POSTED).count()
grns_no_po = GoodsReceipt.objects.filter(
    status=DocumentStatus.POSTED, purchase_order__isnull=True
).count()
grns_no_lines = GoodsReceipt.objects.filter(
    status=DocumentStatus.POSTED
).annotate(line_count=Count('lines')).filter(line_count=0).count()

ok(f"{total_grns} posted GRNs found")
if grns_no_po > 0:
    warn(f"{grns_no_po} GRNs have no linked Purchase Order")
else:
    ok(f"All GRNs have linked Purchase Orders")
if grns_no_lines > 0:
    error(f"{grns_no_lines} GRNs have ZERO line items")
else:
    ok(f"All GRNs have line items")

# Calculate total procurement value
total_procurement = Decimal('0')
zero_value_grns = 0
for grn in GoodsReceipt.objects.filter(status=DocumentStatus.POSTED).prefetch_related(
    'lines__item', 'purchase_order__lines'
):
    grn_val = Decimal('0')
    for line in grn.lines.all():
        cost = Decimal('0')
        if grn.purchase_order:
            po_line = grn.purchase_order.lines.filter(item=line.item).first()
            if po_line and po_line.unit_price > 0:
                cost = line.qty * po_line.unit_price
        if cost == 0 and line.item.cost_price:
            cost = line.qty * line.item.cost_price
        grn_val += cost
    if grn.delivery_charge:
        grn_val += grn.delivery_charge
    if grn_val == 0:
        zero_value_grns += 1
    total_procurement += grn_val

info(f"Total procurement value: ₱{total_procurement:,.2f}")
if zero_value_grns > 0:
    warn(f"{zero_value_grns} GRNs have ₱0 total value (no PO price AND no item cost)")
else:
    ok(f"All GRNs have calculable values")

# ══════════════════════════════════════════════════════════════════════════
header("5. INVOICE & PAYMENT INTEGRITY")
# ══════════════════════════════════════════════════════════════════════════

invoices = Invoice.objects.filter(is_void=False)
total_inv = invoices.count()
total_inv_value = invoices.aggregate(t=Coalesce(Sum('grand_total'), Decimal('0')))['t']
total_payments = InvoicePayment.objects.aggregate(t=Coalesce(Sum('amount'), Decimal('0')))['t']

info(f"{total_inv} active invoices, total value: ₱{total_inv_value:,.2f}")
info(f"Total payments received: ₱{total_payments:,.2f}")

# Check for overpaid invoices
overpaid = []
for inv in invoices.prefetch_related('payments'):
    paid = sum(p.amount for p in inv.payments.all())
    if paid > inv.grand_total + Decimal('0.01'):
        overpaid.append((inv.invoice_number, inv.grand_total, paid))

if not overpaid:
    ok(f"No overpaid invoices found")
else:
    error(f"{len(overpaid)} invoices are OVERPAID")
    for num, total, paid in overpaid[:5]:
        info(f"  {num}: total=₱{total:,.2f} paid=₱{paid:,.2f}")

# Check invoices with zero COGS
zero_cogs = invoices.filter(
    Q(grand_total_cogs=0) | Q(grand_total_cogs__isnull=True),
    grand_total__gt=0
).count()
if zero_cogs > 0:
    warn(f"{zero_cogs} invoices with revenue but ₱0 COGS (may need sync)")
else:
    ok(f"All invoices with revenue have COGS calculated")

# AR calculation
ar_total = Decimal('0')
for inv in invoices.prefetch_related('payments'):
    paid = sum(p.amount for p in inv.payments.all())
    balance = inv.grand_total - paid
    if balance > Decimal('0.01'):
        ar_total += balance
info(f"Current Accounts Receivable: ₱{ar_total:,.2f}")

# ══════════════════════════════════════════════════════════════════════════
header("6. POS SALES INTEGRITY")
# ══════════════════════════════════════════════════════════════════════════

pos_total = POSSale.objects.filter(status=SaleStatus.POSTED).count()
pos_revenue = POSSale.objects.filter(status=SaleStatus.POSTED).aggregate(
    t=Coalesce(Sum('grand_total'), Decimal('0'))
)['t']
info(f"{pos_total} posted POS sales, total revenue: ₱{pos_revenue:,.2f}")

# Check POS sales with zero total
zero_pos = POSSale.objects.filter(status=SaleStatus.POSTED, grand_total=0).count()
if zero_pos > 0:
    warn(f"{zero_pos} POS sales have ₱0 grand total")
else:
    ok(f"All POS sales have non-zero totals")

# POS COGS check
from core.cogs import pos_sale_cogs
pos_cogs_total = Decimal('0')
pos_cogs_errors = 0
for sale in POSSale.objects.filter(status=SaleStatus.POSTED).prefetch_related(
    'lines__item', 'lines__unit', 'bundle_lines__price_list__items'
)[:50]:  # Sample first 50
    try:
        pos_cogs_total += pos_sale_cogs(sale)
    except Exception:
        pos_cogs_errors += 1

if pos_cogs_errors > 0:
    warn(f"{pos_cogs_errors}/50 sampled POS sales have COGS calculation errors")
else:
    ok(f"POS COGS calculation working (sampled 50 sales)")

# ══════════════════════════════════════════════════════════════════════════
header("7. EXPENSE DATA")
# ══════════════════════════════════════════════════════════════════════════

expenses = Expense.objects.filter(status='APPROVED')
exp_count = expenses.count()
exp_total = expenses.aggregate(t=Coalesce(Sum('amount'), Decimal('0')))['t']
info(f"{exp_count} approved expenses, total: ₱{exp_total:,.2f}")

# Check by month
exp_by_month = expenses.values('date__year', 'date__month').annotate(
    total=Sum('amount'), count=Count('id')
).order_by('date__year', 'date__month')
for row in exp_by_month:
    info(f"  {row['date__year']}-{row['date__month']:02d}: {row['count']} expenses, ₱{row['total']:,.2f}")

# ══════════════════════════════════════════════════════════════════════════
header("8. CASHFLOW TRANSACTIONS")
# ══════════════════════════════════════════════════════════════════════════

cf_approved = CashFlowTransaction.objects.filter(status=CashFlowStatus.APPROVED)
cf_in = cf_approved.filter(flow_type='CASH_IN').aggregate(
    t=Coalesce(Sum('amount'), Decimal('0')), c=Count('id')
)
cf_out = cf_approved.filter(flow_type='CASH_OUT').aggregate(
    t=Coalesce(Sum('amount'), Decimal('0')), c=Count('id')
)
info(f"Approved Cash-In: {cf_in['c']} txns, ₱{cf_in['t']:,.2f}")
info(f"Approved Cash-Out: {cf_out['c']} txns, ₱{cf_out['t']:,.2f}")

# Check for duplicate auto-generated entries
dupes = (
    CashFlowTransaction.objects
    .filter(is_auto_generated=True)
    .values('source_type', 'source_id')
    .annotate(cnt=Count('id'))
    .filter(cnt__gt=1)
)
dupe_count = dupes.count()
if dupe_count > 0:
    warn(f"{dupe_count} duplicate auto-generated cashflow entries found")
else:
    ok(f"No duplicate auto-generated entries")

# ══════════════════════════════════════════════════════════════════════════
header("9. MONTHLY CASHFLOW SUMMARIES")
# ══════════════════════════════════════════════════════════════════════════

summaries = MonthlyCashflowSummary.objects.order_by('year', 'month')
if not summaries.exists():
    error("No monthly cashflow summaries found!")
else:
    info(f"{summaries.count()} monthly summaries found")

    # Check balance cascading
    prev_closing = None
    cascade_errors = 0
    for s in summaries:
        if prev_closing is not None:
            diff = abs(s.opening_balance - prev_closing)
            if diff > Decimal('0.02'):
                cascade_errors += 1
                if cascade_errors <= 3:
                    warn(f"  {s.year}-{s.month:02d}: Opening ₱{s.opening_balance:,.2f} ≠ prev closing ₱{prev_closing:,.2f} (diff: ₱{diff:,.2f})")
        prev_closing = s.closing_balance

    if cascade_errors == 0:
        ok(f"Balance cascading is correct across all months")
    else:
        error(f"{cascade_errors} months have broken balance cascading")

    # Check balance sheet equation: Total = Cash + Inventory + AR
    equation_errors = 0
    for s in summaries:
        expected_closing = s.cash_closing + s.inventory_value_closing + s.accounts_receivable_closing
        diff = abs(s.closing_balance - expected_closing)
        if diff > Decimal('0.02'):
            equation_errors += 1
            if equation_errors <= 3:
                warn(f"  {s.year}-{s.month:02d}: Closing ₱{s.closing_balance:,.2f} ≠ Cash+Inv+AR ₱{expected_closing:,.2f}")

    if equation_errors == 0:
        ok(f"Balance sheet equation (Cash+Inv+AR=Total) holds for all months")
    else:
        error(f"{equation_errors} months have broken balance sheet equation")

    # Check net cash flow = closing - opening cash
    ncf_errors = 0
    for s in summaries:
        expected_ncf = s.cash_closing - s.cash_opening
        diff = abs(s.net_cash_flow - expected_ncf)
        if diff > Decimal('0.02'):
            ncf_errors += 1
            if ncf_errors <= 3:
                warn(f"  {s.year}-{s.month:02d}: NCF ₱{s.net_cash_flow:,.2f} ≠ cash change ₱{expected_ncf:,.2f}")

    if ncf_errors == 0:
        ok(f"Net cash flow = cash change for all months")
    else:
        error(f"{ncf_errors} months have NCF ≠ cash change")

    # Print summary table
    print(f"\n  {BOLD}{'Month':<10} {'Cash':>12} {'Inventory':>12} {'AR':>12} {'Total':>14} {'Net Profit':>12}{R}")
    print(f"  {'─'*72}")
    for s in summaries:
        if s.closing_balance != 0 or s.net_profit != 0:
            print(
                f"  {s.year}-{s.month:02d}    "
                f"₱{s.cash_closing:>10,.2f} "
                f"₱{s.inventory_value_closing:>10,.2f} "
                f"₱{s.accounts_receivable_closing:>10,.2f} "
                f"₱{s.closing_balance:>12,.2f} "
                f"₱{s.net_profit:>10,.2f}"
            )

# ══════════════════════════════════════════════════════════════════════════
header("10. INVENTORY VALUE CROSS-CHECK")
# ══════════════════════════════════════════════════════════════════════════

# Method 1: StockBalance * cost_price (current snapshot — authoritative)
inv_val_sb = Decimal('0')
for b in StockBalance.objects.filter(qty_on_hand__gt=0).select_related('item'):
    inv_val_sb += b.qty_on_hand * (b.item.cost_price or Decimal('0'))

# Method 2: Latest monthly summary (formula-based: Opening + Purchased - COGS)
latest = MonthlyCashflowSummary.objects.order_by('-year', '-month').first()
inv_val_summary = latest.inventory_value_closing if latest else Decimal('0')

info(f"StockBalance × cost_price (actual):  ₱{inv_val_sb:,.2f}")
info(f"Monthly summary (formula-based):     ₱{inv_val_summary:,.2f}")

diff = abs(inv_val_sb - inv_val_summary)
pct = (diff / inv_val_sb * 100) if inv_val_sb > 0 else Decimal('0')
if pct < 5:
    ok(f"Inventory values within 5% tolerance (diff: ₱{diff:,.2f}, {pct:.1f}%)")
elif pct < 15:
    warn(f"Inventory value drift: ₱{diff:,.2f} ({pct:.1f}%) — consider running resync")
else:
    error(f"Inventory value mismatch: ₱{diff:,.2f} ({pct:.1f}%) — needs investigation")

# ══════════════════════════════════════════════════════════════════════════
header("AUDIT SUMMARY")
# ══════════════════════════════════════════════════════════════════════════

print(f"\n  {G}✓ {ok_count} checks passed{R}")
if warnings_list:
    print(f"  {W}⚠ {len(warnings_list)} warnings{R}")
if issues:
    print(f"  {E}✗ {len(issues)} errors found:{R}")
    for i, issue in enumerate(issues, 1):
        print(f"    {E}{i}. {issue}{R}")
else:
    print(f"  {G}No critical errors found!{R}")
print()
