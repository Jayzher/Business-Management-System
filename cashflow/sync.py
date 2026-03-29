"""
cashflow/sync.py — Full cash-flow sync.

ALL auto-generated entries are deleted and rebuilt on every sync to ensure
accuracy after retroactive data changes.

sync_weekly_sales_revenue:
  Aggregates all posted sales activity (POS, Delivery/Pickup via Invoice,
  Services via Invoice, minus Sales Returns) into one CASH_IN / SALES entry
  per ISO week.  Amount = weekly revenue.  COGS tracked in notes only.
  The current (incomplete) week is skipped.

sync_procurement_cashflow:
  Rebuilds CASH_OUT for posted GoodsReceipts and CASH_IN for posted
  PurchaseReturns.  Skips if a manual entry with matching amount + date +
  reference already exists.

sync_expense_cashflow:
  Rebuilds CASH_OUT for paid Expenses.  Skips if a manual entry with
  matching amount + date already exists.

sync_all:
  Orchestrates all syncs and returns a combined summary dict.
"""

from decimal import Decimal
from datetime import timedelta, date

from django.db import transaction as db_transaction
from django.utils import timezone


def _monday_of(d):
    """Return the Monday of the ISO week containing date d."""
    # isocalendar returns (ISO year, ISO week, ISO weekday 1=Mon … 7=Sun)
    iso_weekday = d.isocalendar()[2]
    return d - timedelta(days=iso_weekday - 1)


def _week_source_id(d):
    """Encode a date's ISO (year, week) as a single integer YYYYWW."""
    iso = d.isocalendar()
    return iso[0] * 100 + iso[1]


def _sunday_of(d):
    """Return the Sunday (end) of the ISO week containing date d."""
    iso_weekday = d.isocalendar()[2]
    return d + timedelta(days=7 - iso_weekday)


@db_transaction.atomic
def sync_weekly_sales_revenue(user):
    """
    Recalculate weekly revenue and replace ALL WeeklySalesRevenue entries.

    Revenue sources (all combined per ISO week):
      • POS Sales     (POSTED) → grand_total
      • Invoices from Delivery Notes / Sales Pickups → invoice.grand_total
      • Invoices from Customer Services (COMPLETED)  → invoice.grand_total
      • Sales Returns (POSTED) → negative revenue     (refund deduction)

    COGS:
      • POS Sales       → sum(line.item.cost_price × qty)
      • Invoices        → invoice.grand_total_cogs
      • Sales Returns   → reduces COGS (items returned)

    The current (incomplete) week is skipped — only finished weeks are synced.

    Returns the number of new entries created.
    """
    from cashflow.models import (
        CashFlowTransaction, CashFlowCategory, CashFlowType,
        CashFlowStatus, PaymentMethod, CashFlowLog, CashFlowLogAction,
    )
    from core.models import DocumentStatus, Invoice
    from pos.models import POSSale, SaleStatus
    from sales.models import SalesReturn
    from services.models import CustomerService, ServiceStatus

    today = timezone.now().date()
    current_week_key = _week_source_id(today)

    # ── Per-week buckets ──────────────────────────────────────────────────
    buckets = {}

    def _get_bucket(d):
        key = _week_source_id(d)
        if key not in buckets:
            buckets[key] = {
                'revenue': Decimal('0'),
                'cogs': Decimal('0'),
                'monday': _monday_of(d),
                'sunday': _sunday_of(d),
                'iso_year': d.isocalendar()[0],
                'iso_week': d.isocalendar()[1],
            }
        return buckets[key]

    # Track invoice PKs we've already counted to avoid double-counting
    seen_invoice_pks = set()

    # ── 1. POS Sales ──────────────────────────────────────────────────────
    for sale in POSSale.objects.filter(
        status=SaleStatus.POSTED
    ).prefetch_related('lines__item', 'lines__unit', 'invoices'):
        sale_date = sale.posted_at.date() if sale.posted_at else sale.created_at.date()
        b = _get_bucket(sale_date)
        b['revenue'] += sale.grand_total or Decimal('0')
        # COGS: use linked invoice.grand_total_cogs if available
        pos_invoice = sale.invoices.filter(is_void=False).first()
        if pos_invoice and pos_invoice.grand_total_cogs:
            b['cogs'] += pos_invoice.grand_total_cogs
            seen_invoice_pks.add(pos_invoice.pk)
        else:
            for line in sale.lines.all():
                b['cogs'] += (line.item.cost_price or Decimal('0')) * line.qty
            if pos_invoice:
                seen_invoice_pks.add(pos_invoice.pk)

    # ── 2. Invoices from Sales Orders (Delivery Notes / Pickups) ──────────
    for inv in (
        Invoice.objects.filter(
            sales_order__isnull=False,
            is_void=False,
        )
        .exclude(pk__in=seen_invoice_pks)
        .select_related('sales_order')
    ):
        # Only count invoices whose linked SO has at least one POSTED
        # fulfillment (delivery or pickup).  The invoice date is the date.
        so = inv.sales_order
        if not so:
            continue
        has_posted = (
            so.deliveries.filter(status=DocumentStatus.POSTED).exists()
            or so.pickups.filter(status=DocumentStatus.POSTED).exists()
        )
        if not has_posted:
            continue

        b = _get_bucket(inv.date)
        b['revenue'] += inv.grand_total or Decimal('0')
        b['cogs'] += inv.grand_total_cogs or Decimal('0')
        seen_invoice_pks.add(inv.pk)

    # ── 3. Invoices from Customer Services (COMPLETED) ────────────────────
    for svc in (
        CustomerService.objects.filter(
            status=ServiceStatus.COMPLETED,
            invoice__isnull=False,
        )
        .select_related('invoice')
    ):
        inv = svc.invoice
        if inv.pk in seen_invoice_pks or inv.is_void:
            continue
        svc_date = svc.completion_date or svc.service_date
        b = _get_bucket(svc_date)
        b['revenue'] += inv.grand_total or Decimal('0')
        b['cogs'] += inv.grand_total_cogs or Decimal('0')
        seen_invoice_pks.add(inv.pk)

    # ── 4. Sales Returns (reduce revenue and COGS) ────────────────────────
    for sr in SalesReturn.objects.filter(
        status=DocumentStatus.POSTED
    ).select_related('sales_order').prefetch_related('lines__item', 'lines__unit'):
        b = _get_bucket(sr.return_date)
        for line in sr.lines.all():
            b['cogs'] -= (line.item.cost_price or Decimal('0')) * line.qty
            unit_price = Decimal('0')
            if sr.sales_order_id:
                so_line = (
                    sr.sales_order.lines
                    .filter(item=line.item)
                    .only('unit_price')
                    .first()
                )
                if so_line:
                    unit_price = so_line.unit_price
            if unit_price == 0:
                unit_price = line.item.cost_price or Decimal('0')
            b['revenue'] -= unit_price * line.qty

    # ── Delete all existing WeeklySalesRevenue entries ─────────────────────
    CashFlowTransaction.objects.filter(
        source_type='WeeklySalesRevenue',
        is_auto_generated=True,
    ).delete()

    # ── Create one entry per completed week with revenue > 0 ─────────────
    created_count = 0
    for source_id, b in sorted(buckets.items()):
        # Skip the current incomplete week
        if source_id == current_week_key and b['sunday'] > today:
            continue

        revenue = b['revenue']
        if revenue <= 0:
            continue

        gross = revenue - b['cogs']
        iso_year = b['iso_year']
        iso_week = b['iso_week']

        txn = CashFlowTransaction.objects.create(
            transaction_number=CashFlowTransaction.generate_next_number(),
            category=CashFlowCategory.SALES,
            flow_type=CashFlowType.CASH_IN,
            amount=revenue.quantize(Decimal('0.01')),
            transaction_date=b['monday'],
            payment_method=PaymentMethod.CASH,
            reference_no=f'WEEK-{iso_year}-W{iso_week:02d}',
            reason=f'Weekly sales revenue — Week {iso_week:02d} of {iso_year}',
            notes=(
                f'Revenue: ₱{revenue:.2f} | '
                f'COGS: ₱{b["cogs"]:.2f} | '
                f'Gross profit: ₱{gross:.2f}'
            ),
            status=CashFlowStatus.PENDING,
            created_by=user,
            source_type='WeeklySalesRevenue',
            source_id=source_id,
            is_auto_generated=True,
        )

        CashFlowLog.objects.create(
            transaction=txn,
            action=CashFlowLogAction.CREATED,
            performed_by=user,
            details=(
                f'Sync: weekly revenue for Week {iso_week:02d}/{iso_year}. '
                f'Revenue=₱{revenue:.2f}, COGS=₱{b["cogs"]:.2f}, '
                f'Gross=₱{gross:.2f}.'
            ),
        )
        created_count += 1

    return created_count


# ═══════════════════════════════════════════════════════════════════════════
# PROCUREMENT SYNC — rebuild GoodsReceipts & PurchaseReturns
# ═══════════════════════════════════════════════════════════════════════════

def _manual_entry_exists(amount, txn_date, flow_type, reference_no=''):
    """
    Return True if a *manual* CashFlowTransaction already covers this exact
    amount + date (+ optional reference).  Used to avoid duplicating a
    hand-entered entry with an auto-generated one.
    """
    from cashflow.models import CashFlowTransaction
    qs = CashFlowTransaction.objects.filter(
        is_auto_generated=False,
        amount=amount,
        transaction_date=txn_date,
        flow_type=flow_type,
    )
    if reference_no:
        qs = qs.filter(reference_no=reference_no)
    return qs.exists()


@db_transaction.atomic
def sync_procurement_cashflow(user):
    """
    Delete all auto-generated GoodsReceipt / PurchaseReturn entries and
    rebuild them.  Skips if a matching manual entry already exists.

    Returns (grn_count, pr_count).
    """
    from cashflow.models import (
        CashFlowTransaction, CashFlowCategory, CashFlowType,
        CashFlowStatus, PaymentMethod, CashFlowLog, CashFlowLogAction,
    )
    from core.models import DocumentStatus
    from procurement.models import GoodsReceipt, PurchaseReturn

    # ── Wipe previous auto-generated procurement entries ──────────────────
    CashFlowTransaction.objects.filter(
        source_type__in=['GoodsReceipt', 'PurchaseReturn'],
        is_auto_generated=True,
    ).delete()

    # ── GoodsReceipts (CASH_OUT / PROCUREMENT) ────────────────────────────
    grn_count = 0
    for grn in (
        GoodsReceipt.objects.filter(status=DocumentStatus.POSTED)
        .select_related('purchase_order', 'supplier')
        .prefetch_related('lines__item', 'lines__unit')
    ):
        total = Decimal('0')
        for line in grn.lines.all():
            unit_price = Decimal('0')
            if grn.purchase_order_id:
                po_line = (
                    grn.purchase_order.lines
                    .filter(item=line.item)
                    .only('unit_price')
                    .first()
                )
                if po_line:
                    unit_price = po_line.unit_price
            if unit_price == 0:
                unit_price = getattr(line.item, 'cost_price', None) or Decimal('0')
            total += line.qty * unit_price

        if total <= 0:
            continue

        total = total.quantize(Decimal('0.01'))

        # Skip if a manual entry already covers this exact GRN
        if _manual_entry_exists(total, grn.receipt_date, 'CASH_OUT', grn.document_number):
            continue

        grn_user = grn.posted_by or grn.created_by or user
        supplier_name = grn.supplier.name if grn.supplier_id else 'Unknown supplier'

        txn = CashFlowTransaction.objects.create(
            transaction_number=CashFlowTransaction.generate_next_number(),
            category=CashFlowCategory.PROCUREMENT,
            flow_type=CashFlowType.CASH_OUT,
            amount=total,
            transaction_date=grn.receipt_date,
            payment_method=PaymentMethod.CASH,
            reference_no=grn.document_number,
            reason=f'Goods received: {grn.document_number} from {supplier_name}',
            status=CashFlowStatus.PENDING,
            created_by=grn_user,
            source_type='GoodsReceipt',
            source_id=grn.pk,
            is_auto_generated=True,
        )
        CashFlowLog.objects.create(
            transaction=txn,
            action=CashFlowLogAction.CREATED,
            performed_by=grn_user,
            details=f'Sync: auto-generated from GoodsReceipt {grn.document_number}.',
        )
        grn_count += 1

    # ── PurchaseReturns (CASH_IN / PROCUREMENT) ───────────────────────────
    pr_count = 0
    for pr in (
        PurchaseReturn.objects.filter(status=DocumentStatus.POSTED)
        .select_related('goods_receipt__purchase_order', 'supplier')
        .prefetch_related('lines__item')
    ):
        total = Decimal('0')
        for line in pr.lines.all():
            unit_price = Decimal('0')
            if pr.goods_receipt_id:
                grn = pr.goods_receipt
                if grn.purchase_order_id:
                    po_line = (
                        grn.purchase_order.lines
                        .filter(item=line.item)
                        .only('unit_price')
                        .first()
                    )
                    if po_line:
                        unit_price = po_line.unit_price
            if not unit_price:
                unit_price = getattr(line.item, 'cost_price', None) or Decimal('0')
            total += line.qty * unit_price

        if total <= 0:
            continue

        total = total.quantize(Decimal('0.01'))

        if _manual_entry_exists(total, pr.return_date, 'CASH_IN', pr.document_number):
            continue

        pr_user = pr.posted_by or pr.created_by or user
        supplier_name = pr.supplier.name if pr.supplier_id else 'Unknown supplier'

        txn = CashFlowTransaction.objects.create(
            transaction_number=CashFlowTransaction.generate_next_number(),
            category=CashFlowCategory.PROCUREMENT,
            flow_type=CashFlowType.CASH_IN,
            amount=total,
            transaction_date=pr.return_date,
            payment_method=PaymentMethod.CASH,
            reference_no=pr.document_number,
            reason=f'Purchase return: {pr.document_number} to {supplier_name}',
            status=CashFlowStatus.PENDING,
            created_by=pr_user,
            source_type='PurchaseReturn',
            source_id=pr.pk,
            is_auto_generated=True,
        )
        CashFlowLog.objects.create(
            transaction=txn,
            action=CashFlowLogAction.CREATED,
            performed_by=pr_user,
            details=f'Sync: auto-generated from PurchaseReturn {pr.document_number}.',
        )
        pr_count += 1

    return grn_count, pr_count


# ═══════════════════════════════════════════════════════════════════════════
# EXPENSE SYNC — rebuild paid Expenses
# ═══════════════════════════════════════════════════════════════════════════

@db_transaction.atomic
def sync_expense_cashflow(user):
    """
    Delete all auto-generated Expense entries and rebuild them.
    Skips if a matching manual entry already exists (same amount + date).

    Returns the number of new entries created.
    """
    from cashflow.models import (
        CashFlowTransaction, CashFlowCategory, CashFlowType,
        CashFlowStatus, PaymentMethod, CashFlowLog, CashFlowLogAction,
    )
    from core.models import Expense, ExpenseStatus

    # ── Wipe previous auto-generated expense entries ──────────────────────
    CashFlowTransaction.objects.filter(
        source_type='Expense',
        is_auto_generated=True,
    ).delete()

    created_count = 0
    for exp in (
        Expense.objects.filter(status=ExpenseStatus.PAID)
        .select_related('category', 'created_by')
    ):
        if exp.amount <= 0:
            continue

        amount = exp.amount.quantize(Decimal('0.01')) if hasattr(exp.amount, 'quantize') else Decimal(str(exp.amount))

        # Skip if a manual entry already covers this exact expense
        if _manual_entry_exists(amount, exp.date, 'CASH_OUT', exp.reference_no or ''):
            continue

        reason = (
            f'{exp.category.name}: {exp.item_description}'
            if exp.item_description
            else exp.category.name
        )

        txn = CashFlowTransaction.objects.create(
            transaction_number=CashFlowTransaction.generate_next_number(),
            category=CashFlowCategory.EXPENSES,
            flow_type=CashFlowType.CASH_OUT,
            amount=amount,
            transaction_date=exp.date,
            payment_method=PaymentMethod.CASH,
            reference_no=exp.reference_no or '',
            reason=reason,
            notes=exp.memo or '',
            status=CashFlowStatus.PENDING,
            created_by=exp.created_by or user,
            source_type='Expense',
            source_id=exp.pk,
            is_auto_generated=True,
        )
        CashFlowLog.objects.create(
            transaction=txn,
            action=CashFlowLogAction.CREATED,
            performed_by=exp.created_by or user,
            details=f'Sync: auto-generated from Expense #{exp.pk}.',
        )
        created_count += 1

    return created_count


# ═══════════════════════════════════════════════════════════════════════════
# SYNC ALL — orchestrate a full cash-flow sync
# ═══════════════════════════════════════════════════════════════════════════

def sync_all(user):
    """
    Run all sync functions and return a summary dict.

    Returns dict with keys: sales, grn, purchase_return, expense, errors.
    Each error is a string describing which module failed and why.
    """
    results = {
        'sales': 0,
        'grn': 0,
        'purchase_return': 0,
        'expense': 0,
        'errors': [],
    }

    try:
        results['sales'] = sync_weekly_sales_revenue(user)
    except Exception as exc:
        results['errors'].append(f'Sales sync failed: {exc}')

    try:
        grn_count, pr_count = sync_procurement_cashflow(user)
        results['grn'] = grn_count
        results['purchase_return'] = pr_count
    except Exception as exc:
        results['errors'].append(f'Procurement sync failed: {exc}')

    try:
        results['expense'] = sync_expense_cashflow(user)
    except Exception as exc:
        results['errors'].append(f'Expense sync failed: {exc}')

    return results
