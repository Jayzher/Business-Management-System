"""
Management command: calculate_financial_statements
===================================================
Calculates comprehensive financial statements including:
- Cash Flow Statement (actual cash movement)
- Profit & Loss Statement (accrual basis)
- Balance Sheet metrics (AR, AP, Inventory)
- Performance metrics (DSO, collection rate, inventory turnover)

Usage:
    python manage.py calculate_financial_statements --year 2026 --month 4
    python manage.py calculate_financial_statements --year 2026
    python manage.py calculate_financial_statements --dry-run
"""
from decimal import Decimal
from datetime import date
from calendar import monthrange

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Sum, Q
from django.utils import timezone

from cashflow.models import MonthlyCashflowSummary
from core.models import Invoice, InvoicePayment, Expense, DocumentStatus
from pos.models import POSSale, SaleStatus
from procurement.models import GoodsReceipt
from inventory.models import StockBalance


class Command(BaseCommand):
    help = 'Calculate comprehensive financial statements'

    def add_arguments(self, parser):
        parser.add_argument('--year', type=int, help='Year to calculate')
        parser.add_argument('--month', type=int, help='Month to calculate (1-12)')
        parser.add_argument('--dry-run', action='store_true', help='Preview without saving')
        parser.add_argument('--quiet', '-q', action='store_true', help='Suppress output')

    def handle(self, *args, **options):
        year = options.get('year')
        month = options.get('month')
        dry_run = options['dry_run']
        self.quiet = options['quiet']

        if month and not year:
            self.stdout.write(self.style.ERROR('--month requires --year'))
            return

        mode = 'DRY-RUN' if dry_run else 'APPLYING'
        self.stdout.write(self.style.SUCCESS(f'\n=== Financial Statements Calculator [{mode}] ===\n'))

        # Determine periods
        if year and month:
            periods = [(year, month)]
        elif year:
            periods = [(year, m) for m in range(1, 13)]
        else:
            periods = self._get_all_periods()

        if not periods:
            self.stdout.write(self.style.WARNING('No data found.'))
            return

        self.stdout.write(f'Calculating {len(periods)} month(s)...\n')

        with transaction.atomic():
            for yr, mn in periods:
                self._calculate_month(yr, mn, dry_run)

            if dry_run:
                transaction.set_rollback(True)
                self.stdout.write(self.style.WARNING('\nDry-run complete. No changes saved.'))
            else:
                self.stdout.write(self.style.SUCCESS('\n=== Calculation Complete ==='))

    def _get_all_periods(self):
        """Get all months with transaction data."""
        periods = set()
        
        # From invoices
        for dt in Invoice.objects.values_list('date', flat=True).distinct():
            if dt:
                periods.add((dt.year, dt.month))
        
        # From POS sales
        for dt in POSSale.objects.filter(status=SaleStatus.POSTED).values_list('posted_at', flat=True).distinct():
            if dt:
                periods.add((dt.year, dt.month))
        
        # From GRNs
        for dt in GoodsReceipt.objects.filter(status=DocumentStatus.POSTED).values_list('receipt_date', flat=True).distinct():
            if dt:
                periods.add((dt.year, dt.month))
        
        return sorted(periods)

    def _calculate_month(self, year, month, dry_run):
        """Calculate all financial statements for a specific month."""
        from calendar import month_name
        
        self._info(f'\n{"="*80}')
        self._info(f'  {month_name[month]} {year}')
        self._info(f'{"="*80}\n')

        # Date range
        start_date = date(year, month, 1)
        last_day = monthrange(year, month)[1]
        end_date = date(year, month, last_day)
        
        if month == 12:
            next_month_start = date(year + 1, 1, 1)
        else:
            next_month_start = date(year, month + 1, 1)

        # ══════════════════════════════════════════════════════════════════════
        # 1. INVENTORY METRICS
        # ══════════════════════════════════════════════════════════════════════
        inventory_opening = self._calculate_inventory_value(start_date)
        inventory_closing = self._calculate_inventory_value(end_date)
        inventory_purchased = self._calculate_procurement_costs(start_date, next_month_start)
        cogs_actual = self._calculate_actual_cogs(start_date, next_month_start)
        
        # Inventory turnover = COGS / Average Inventory
        avg_inventory = (inventory_opening + inventory_closing) / 2
        inventory_turnover = (cogs_actual / avg_inventory) if avg_inventory > 0 else Decimal('0')

        # ══════════════════════════════════════════════════════════════════════
        # 2. ACCOUNTS RECEIVABLE & PAYABLE
        # ══════════════════════════════════════════════════════════════════════
        ar_opening = self._calculate_ar(start_date)
        ar_closing = self._calculate_ar(next_month_start)
        ap_opening = self._calculate_ap(start_date)
        ap_closing = self._calculate_ap(next_month_start)

        # ══════════════════════════════════════════════════════════════════════
        # 3. PROFIT & LOSS STATEMENT (Accrual Basis)
        # ══════════════════════════════════════════════════════════════════════
        revenue_accrual = self._calculate_revenue_accrual(start_date, next_month_start)
        gross_profit = revenue_accrual - cogs_actual
        gross_margin_pct = (gross_profit / revenue_accrual * 100) if revenue_accrual > 0 else Decimal('0')
        
        operational_expenses = self._calculate_operational_expenses(start_date, next_month_start)
        other_expenses = self._calculate_other_cash_out(start_date, next_month_start)
        total_expenses = cogs_actual + operational_expenses + other_expenses
        net_profit = revenue_accrual - total_expenses

        # ══════════════════════════════════════════════════════════════════════
        # 4. CASH FLOW STATEMENT (Cash Basis)
        # ══════════════════════════════════════════════════════════════════════
        cash_from_customers = self._calculate_cash_from_customers(start_date, next_month_start)
        cash_to_suppliers = self._calculate_cash_to_suppliers(start_date, next_month_start)
        cash_for_operations = operational_expenses  # Assume paid immediately
        cash_other_out = other_expenses
        
        operating_cash_flow = cash_from_customers - cash_to_suppliers - cash_for_operations - cash_other_out
        
        # Get previous month's closing cash
        if month == 1:
            prev_summary = MonthlyCashflowSummary.objects.filter(year=year - 1, month=12).first()
        else:
            prev_summary = MonthlyCashflowSummary.objects.filter(year=year, month=month - 1).first()
        
        cash_opening = prev_summary.cash_closing if prev_summary else Decimal('0')
        cash_closing = cash_opening + operating_cash_flow

        # ══════════════════════════════════════════════════════════════════════
        # 5. PERFORMANCE METRICS
        # ══════════════════════════════════════════════════════════════════════
        # Collection Rate = Cash Collected / Revenue Invoiced
        collection_rate_pct = (cash_from_customers / revenue_accrual * 100) if revenue_accrual > 0 else Decimal('0')
        
        # Days Sales Outstanding = (AR / Revenue) * Days in Month
        days_in_month = last_day
        dso = (ar_closing / revenue_accrual * days_in_month) if revenue_accrual > 0 else Decimal('0')

        # ══════════════════════════════════════════════════════════════════════
        # 6. OPENING/CLOSING BALANCE (Total Assets)
        # ══════════════════════════════════════════════════════════════════════
        opening_balance = cash_opening + inventory_opening + ar_opening
        closing_balance = cash_closing + inventory_closing + ar_closing

        # ══════════════════════════════════════════════════════════════════════
        # DISPLAY SUMMARY
        # ══════════════════════════════════════════════════════════════════════
        self._display_summary(
            cash_opening, cash_closing, cash_from_customers, cash_to_suppliers,
            operating_cash_flow, revenue_accrual, cogs_actual, gross_profit,
            gross_margin_pct, operational_expenses, other_expenses, net_profit,
            inventory_opening, inventory_closing, inventory_purchased, inventory_turnover,
            ar_opening, ar_closing, ap_opening, ap_closing,
            collection_rate_pct, dso, opening_balance, closing_balance
        )

        # ══════════════════════════════════════════════════════════════════════
        # SAVE TO DATABASE
        # ══════════════════════════════════════════════════════════════════════
        if not dry_run:
            summary, created = MonthlyCashflowSummary.objects.update_or_create(
                year=year,
                month=month,
                defaults={
                    # Opening/Closing
                    'opening_balance': opening_balance,
                    'closing_balance': closing_balance,
                    
                    # Cash Flow
                    'cash_opening': cash_opening,
                    'cash_closing': cash_closing,
                    'cash_from_customers': cash_from_customers,
                    'cash_to_suppliers': cash_to_suppliers,
                    'operating_cash_flow': operating_cash_flow,
                    
                    # AR/AP
                    'accounts_receivable_opening': ar_opening,
                    'accounts_receivable_closing': ar_closing,
                    'accounts_payable_opening': ap_opening,
                    'accounts_payable_closing': ap_closing,
                    
                    # P&L
                    'revenue_accrual': revenue_accrual,
                    'cogs_actual': cogs_actual,
                    'gross_profit': gross_profit,
                    'gross_margin_pct': gross_margin_pct,
                    'net_profit': net_profit,
                    
                    # Inventory
                    'inventory_value_opening': inventory_opening,
                    'inventory_value_closing': inventory_closing,
                    'inventory_purchased': inventory_purchased,
                    'inventory_turnover': inventory_turnover,
                    
                    # Performance Metrics
                    'collection_rate_pct': collection_rate_pct,
                    'days_sales_outstanding': dso,
                    
                    # Legacy fields
                    'capital_sales': revenue_accrual,
                    'capital_total': revenue_accrual,
                    'expenses_procurement': inventory_purchased,
                    'expenses_operational': operational_expenses,
                    'expenses_other': other_expenses,
                    'expenses_total': total_expenses,
                    'total_inflow': revenue_accrual,
                    'total_outflow': total_expenses,
                    'net_cash_flow': operating_cash_flow,
                    
                    'calculated_at': timezone.now(),
                }
            )
            action = 'Created' if created else 'Updated'
            self._info(f'\n  ✓ {action} financial summary')

    def _display_summary(self, cash_opening, cash_closing, cash_from_customers, cash_to_suppliers,
                        operating_cash_flow, revenue_accrual, cogs_actual, gross_profit,
                        gross_margin_pct, operational_expenses, other_expenses, net_profit,
                        inventory_opening, inventory_closing, inventory_purchased, inventory_turnover,
                        ar_opening, ar_closing, ap_opening, ap_closing,
                        collection_rate_pct, dso, opening_balance, closing_balance):
        """Display formatted financial summary."""
        
        self._info('┌─ BALANCE SHEET ─────────────────────────────────────────────────────┐')
        self._info(f'│ Opening Balance (Total Assets):    {self._fmt(opening_balance):>20} │')
        self._info(f'│   • Cash:                          {self._fmt(cash_opening):>20} │')
        self._info(f'│   • Inventory:                     {self._fmt(inventory_opening):>20} │')
        self._info(f'│   • Accounts Receivable:           {self._fmt(ar_opening):>20} │')
        self._info('├─────────────────────────────────────────────────────────────────────┤')
        self._info(f'│ Closing Balance (Total Assets):    {self._fmt(closing_balance):>20} │')
        self._info(f'│   • Cash:                          {self._fmt(cash_closing):>20} │')
        self._info(f'│   • Inventory:                     {self._fmt(inventory_closing):>20} │')
        self._info(f'│   • Accounts Receivable:           {self._fmt(ar_closing):>20} │')
        self._info('└─────────────────────────────────────────────────────────────────────┘\n')
        
        self._info('┌─ CASH FLOW STATEMENT (Actual Cash Movement) ────────────────────────┐')
        self._info(f'│ Cash from Customers:               {self._fmt(cash_from_customers):>20} │')
        self._info(f'│ Cash to Suppliers:                 {self._fmt(-cash_to_suppliers):>20} │')
        self._info(f'│ Operating Expenses:                {self._fmt(-operational_expenses):>20} │')
        self._info(f'│ Other Cash Out:                    {self._fmt(-other_expenses):>20} │')
        self._info('├─────────────────────────────────────────────────────────────────────┤')
        self._info(f'│ Net Operating Cash Flow:           {self._fmt(operating_cash_flow):>20} │')
        self._info('└─────────────────────────────────────────────────────────────────────┘\n')
        
        self._info('┌─ PROFIT & LOSS STATEMENT (Accrual Basis) ───────────────────────────┐')
        self._info(f'│ Revenue (Invoiced):                {self._fmt(revenue_accrual):>20} │')
        self._info(f'│ Cost of Goods Sold:                {self._fmt(-cogs_actual):>20} │')
        self._info('├─────────────────────────────────────────────────────────────────────┤')
        self._info(f'│ Gross Profit:                      {self._fmt(gross_profit):>20} │')
        self._info(f'│ Gross Margin:                      {gross_margin_pct:>19.2f}% │')
        self._info('├─────────────────────────────────────────────────────────────────────┤')
        self._info(f'│ Operating Expenses:                {self._fmt(-operational_expenses):>20} │')
        self._info(f'│ Other Expenses:                    {self._fmt(-other_expenses):>20} │')
        self._info('├─────────────────────────────────────────────────────────────────────┤')
        self._info(f'│ Net Profit:                        {self._fmt(net_profit):>20} │')
        self._info('└─────────────────────────────────────────────────────────────────────┘\n')
        
        self._info('┌─ PERFORMANCE METRICS ────────────────────────────────────────────────┐')
        self._info(f'│ Collection Rate:                   {collection_rate_pct:>19.2f}% │')
        self._info(f'│ Days Sales Outstanding (DSO):      {dso:>19.1f} days │')
        self._info(f'│ Inventory Turnover:                {inventory_turnover:>19.2f}x │')
        self._info(f'│ Inventory Purchased:               {self._fmt(inventory_purchased):>20} │')
        self._info('└─────────────────────────────────────────────────────────────────────┘\n')

    def _fmt(self, amount):
        """Format currency amount."""
        return f'₱{amount:,.2f}'

    # ══════════════════════════════════════════════════════════════════════════
    # CALCULATION HELPERS
    # ══════════════════════════════════════════════════════════════════════════

    def _calculate_inventory_value(self, as_of_date):
        """Calculate inventory value as of date."""
        total = Decimal('0')
        for balance in StockBalance.objects.filter(qty_on_hand__gt=0).select_related('item'):
            cost = balance.item.cost_price or Decimal('0')
            total += balance.qty_on_hand * cost
        return total

    def _calculate_ar(self, as_of_date):
        """Calculate accounts receivable (unpaid invoices) as of date."""
        total = Decimal('0')
        invoices = Invoice.objects.filter(
            is_void=False,
            date__lt=as_of_date,
        ).prefetch_related('payments')
        
        for inv in invoices:
            paid = sum(p.amount for p in inv.payments.filter(date__lt=as_of_date))
            balance = inv.grand_total - paid
            if balance > 0:
                total += balance
        
        return total

    def _calculate_ap(self, as_of_date):
        """Calculate accounts payable (unpaid bills) as of date."""
        # For now, assume all procurement is paid immediately
        # TODO: Implement supplier payment tracking
        return Decimal('0')

    def _calculate_revenue_accrual(self, start_date, end_date):
        """Calculate revenue on accrual basis (when invoiced)."""
        total = Decimal('0')
        
        # Invoices
        invoices = Invoice.objects.filter(
            is_void=False,
            date__gte=start_date,
            date__lt=end_date,
        )
        total += invoices.aggregate(Sum('grand_total'))['grand_total__sum'] or Decimal('0')
        
        # POS Sales
        pos_sales = POSSale.objects.filter(
            status=SaleStatus.POSTED,
            posted_at__gte=start_date,
            posted_at__lt=end_date,
        )
        total += pos_sales.aggregate(Sum('grand_total'))['grand_total__sum'] or Decimal('0')
        
        return total

    def _calculate_cash_from_customers(self, start_date, end_date):
        """Calculate actual cash received from customers."""
        total = Decimal('0')
        
        # Invoice payments
        payments = InvoicePayment.objects.filter(
            date__gte=start_date,
            date__lt=end_date,
        )
        total += payments.aggregate(Sum('amount'))['amount__sum'] or Decimal('0')
        
        # POS sales (assume immediate payment)
        pos_sales = POSSale.objects.filter(
            status=SaleStatus.POSTED,
            posted_at__gte=start_date,
            posted_at__lt=end_date,
        )
        total += pos_sales.aggregate(Sum('grand_total'))['grand_total__sum'] or Decimal('0')
        
        return total

    def _calculate_actual_cogs(self, start_date, end_date):
        """Calculate COGS from sales."""
        from core.cogs import pos_sale_cogs
        total = Decimal('0')
        
        # POS COGS
        for sale in POSSale.objects.filter(status=SaleStatus.POSTED, posted_at__gte=start_date, posted_at__lt=end_date).prefetch_related('lines__item', 'bundle_lines__price_list__items'):
            try:
                total += pos_sale_cogs(sale)
            except:
                pass
        
        # Invoice COGS
        invoices = Invoice.objects.filter(is_void=False, date__gte=start_date, date__lt=end_date)
        total += invoices.aggregate(Sum('grand_total_cogs'))['grand_total_cogs__sum'] or Decimal('0')
        
        return total

    def _calculate_procurement_costs(self, start_date, end_date):
        """Calculate procurement costs."""
        total = Decimal('0')
        for grn in GoodsReceipt.objects.filter(status=DocumentStatus.POSTED, receipt_date__gte=start_date, receipt_date__lt=end_date).prefetch_related('lines', 'purchase_order__lines'):
            for line in grn.lines.all():
                if grn.purchase_order:
                    po_line = grn.purchase_order.lines.filter(item=line.item).first()
                    if po_line:
                        total += line.qty * po_line.unit_price
            total += grn.delivery_charge or Decimal('0')
        return total

    def _calculate_cash_to_suppliers(self, start_date, end_date):
        """Calculate cash paid to suppliers (assume immediate payment for now)."""
        return self._calculate_procurement_costs(start_date, end_date)

    def _calculate_operational_expenses(self, start_date, end_date):
        """Calculate operational expenses."""
        expenses = Expense.objects.filter(
            status='APPROVED',
            date__gte=start_date,
            date__lt=end_date,
            category__is_cogs=False,
        )
        return expenses.aggregate(Sum('amount'))['amount__sum'] or Decimal('0')

    def _calculate_other_cash_out(self, start_date, end_date):
        """Calculate other cash out."""
        from cashflow.models import CashFlowTransaction, CashFlowType, CashFlowStatus, CashFlowCategory
        txns = CashFlowTransaction.objects.filter(
            status=CashFlowStatus.APPROVED,
            flow_type=CashFlowType.CASH_OUT,
            transaction_date__gte=start_date,
            transaction_date__lt=end_date,
        ).exclude(category__in=[CashFlowCategory.PROCUREMENT, CashFlowCategory.EXPENSES])
        return txns.aggregate(Sum('amount'))['amount__sum'] or Decimal('0')

    def _info(self, msg):
        """Print info message unless quiet."""
        if not self.quiet:
            self.stdout.write(msg)
