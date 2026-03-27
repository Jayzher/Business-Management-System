"""
cashflow/sync.py — Weekly sales gross-profit sync.

Aggregates all posted sales activity (POS, Delivery Notes, Sales Pickups,
minus Sales Returns) into a single CASH_IN / SALES  entry per ISO week.

  Entry amount = Weekly Revenue − Weekly COGS

Revenue comes from:
  • POSSale (POSTED)           → grand_total
  • DeliveryNote (POSTED)      → qty × SO line unit_price per line
  • SalesPickup (POSTED)       → qty × SO line unit_price per line
  • SalesReturn (POSTED)       → negative revenue (refund)

COGS comes from item.cost_price × qty for confirmed sales lines.
SalesReturn lines *reduce* COGS (items came back to stock).

Existing WeeklySalesRevenue entries are always deleted and regenerated so
the numbers remain accurate after any retroactive data changes.

Usage:
    from cashflow.sync import sync_weekly_sales_revenue
    count = sync_weekly_sales_revenue(request.user)
"""

from decimal import Decimal
from datetime import timedelta

from django.db import transaction as db_transaction


def _monday_of(d):
    """Return the Monday of the ISO week containing date d."""
    # isocalendar returns (ISO year, ISO week, ISO weekday 1=Mon … 7=Sun)
    iso_weekday = d.isocalendar()[2]
    return d - timedelta(days=iso_weekday - 1)


def _week_source_id(d):
    """Encode a date's ISO (year, week) as a single integer YYYYWW."""
    iso = d.isocalendar()
    return iso[0] * 100 + iso[1]


@db_transaction.atomic
def sync_weekly_sales_revenue(user):
    """
    Recalculate weekly gross profit and replace all WeeklySalesRevenue
    cash-flow entries.

    Returns the number of new entries created.
    """
    from cashflow.models import (
        CashFlowTransaction, CashFlowCategory, CashFlowType,
        CashFlowStatus, PaymentMethod, CashFlowLog, CashFlowLogAction,
    )
    from core.models import DocumentStatus
    from pos.models import POSSale, SaleStatus
    from sales.models import DeliveryNote, SalesPickup, SalesReturn

    # ── Accumulate per-week buckets ────────────────────────────────────────
    # Each bucket: {'revenue': Decimal, 'cogs': Decimal, 'monday': date}
    buckets = {}

    def _get_bucket(d):
        key = _week_source_id(d)
        if key not in buckets:
            buckets[key] = {
                'revenue': Decimal('0'),
                'cogs': Decimal('0'),
                'monday': _monday_of(d),
                'iso_year': d.isocalendar()[0],
                'iso_week': d.isocalendar()[1],
            }
        return buckets[key]

    # ── POS Sales ──────────────────────────────────────────────────────────
    for sale in POSSale.objects.filter(
        status=SaleStatus.POSTED
    ).prefetch_related('lines__item', 'lines__unit'):
        sale_date = sale.posted_at.date() if sale.posted_at else sale.created_at.date()
        b = _get_bucket(sale_date)
        b['revenue'] += sale.grand_total or Decimal('0')
        for line in sale.lines.all():
            b['cogs'] += (line.item.cost_price or Decimal('0')) * line.qty

    # ── Delivery Notes ─────────────────────────────────────────────────────
    for dn in DeliveryNote.objects.filter(
        status=DocumentStatus.POSTED
    ).select_related('sales_order').prefetch_related('lines__item', 'lines__unit'):
        b = _get_bucket(dn.delivery_date)
        for line in dn.lines.all():
            b['cogs'] += (line.item.cost_price or Decimal('0')) * line.qty
            unit_price = Decimal('0')
            if dn.sales_order_id:
                so_line = (
                    dn.sales_order.lines
                    .filter(item=line.item)
                    .only('unit_price')
                    .first()
                )
                if so_line:
                    unit_price = so_line.unit_price
            b['revenue'] += unit_price * line.qty

    # ── Sales Pickups ──────────────────────────────────────────────────────
    for pu in SalesPickup.objects.filter(
        status=DocumentStatus.POSTED
    ).select_related('sales_order').prefetch_related('lines__item', 'lines__unit'):
        b = _get_bucket(pu.pickup_date)
        for line in pu.lines.all():
            b['cogs'] += (line.item.cost_price or Decimal('0')) * line.qty
            unit_price = Decimal('0')
            if pu.sales_order_id:
                so_line = (
                    pu.sales_order.lines
                    .filter(item=line.item)
                    .only('unit_price')
                    .first()
                )
                if so_line:
                    unit_price = so_line.unit_price
            b['revenue'] += unit_price * line.qty

    # ── Sales Returns (reduce both revenue and COGS for that week) ─────────
    for sr in SalesReturn.objects.filter(
        status=DocumentStatus.POSTED
    ).select_related('sales_order').prefetch_related('lines__item', 'lines__unit'):
        b = _get_bucket(sr.return_date)
        for line in sr.lines.all():
            # Returned items reduce COGS
            b['cogs'] -= (line.item.cost_price or Decimal('0')) * line.qty
            # Revenue reduction (refund to customer)
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

    # ── Replace all existing WeeklySalesRevenue entries ───────────────────
    CashFlowTransaction.objects.filter(
        source_type='WeeklySalesRevenue',
        is_auto_generated=True,
    ).delete()

    # ── Create one entry per week where gross profit > 0 ──────────────────
    created_count = 0
    for source_id, b in sorted(buckets.items()):
        gross = b['revenue'] - b['cogs']
        if gross <= 0:
            continue  # Week with no profitable sales — skip

        iso_year = b['iso_year']
        iso_week = b['iso_week']

        txn = CashFlowTransaction.objects.create(
            transaction_number=CashFlowTransaction.generate_next_number(),
            category=CashFlowCategory.SALES,
            flow_type=CashFlowType.CASH_IN,
            amount=gross.quantize(Decimal('0.01')),
            transaction_date=b['monday'],
            payment_method=PaymentMethod.CASH,
            reference_no=f'WEEK-{iso_year}-W{iso_week:02d}',
            reason=f'Weekly gross profit — Week {iso_week:02d} of {iso_year}',
            notes=(
                f'Revenue: ₱{b["revenue"]:.2f} | '
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
                f'Sync: weekly gross profit for Week {iso_week:02d}/{iso_year}. '
                f'Revenue=₱{b["revenue"]:.2f}, COGS=₱{b["cogs"]:.2f}.'
            ),
        )
        created_count += 1

    return created_count
