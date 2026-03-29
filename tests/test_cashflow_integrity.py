"""
Cashflow Integrity Test
========================
Verifies that the cashflow sync produces correct entries and detects
duplicate manual + automated cash-out / cash-in entries.

Run:
    python manage.py test tests.test_cashflow_integrity --verbosity=2
"""

from decimal import Decimal
from datetime import date, timedelta

from django.test import TestCase
from django.contrib.auth import get_user_model

User = get_user_model()


class CashflowSyncIntegrityTest(TestCase):
    """Test that sync_all produces correct, non-duplicate cash flow entries."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username='cftest', password='testpass123',
        )
        # Shared fixtures
        from catalog.models import Category, Unit
        from warehouses.models import Warehouse, Location
        from partners.models import Supplier, Customer

        cls.unit = Unit.objects.create(name='Piece', abbreviation='pc')
        cls.category = Category.objects.create(name='General', code='GEN')
        cls.warehouse = Warehouse.objects.create(code='TWH', name='Test WH')
        cls.location = Location.objects.create(
            warehouse=cls.warehouse, name='Shelf A', code='A1',
        )
        cls.supplier = Supplier.objects.create(code='SUP01', name='Test Supplier')
        cls.customer = Customer.objects.create(code='CUS01', name='Test Customer')

        # POS register + shift
        from pos.models import POSRegister, POSShift
        from django.utils import timezone as tz
        cls.register = POSRegister.objects.create(
            name='R1', warehouse=cls.warehouse,
            default_location=cls.location,
        )
        cls.shift = POSShift.objects.create(
            register=cls.register,
            opened_by=cls.user,
            opened_at=tz.now(),
        )

    # ──────────────────────────────────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────────────────────────────────

    def _create_item(self, code, name, cost_price, selling_price):
        from catalog.models import Item
        return Item.objects.create(
            code=code, name=name,
            cost_price=cost_price,
            selling_price=selling_price,
            category=self.category,
            default_unit=self.unit,
        )

    def _last_monday(self):
        """Return the Monday of last week (guaranteed completed week)."""
        today = date.today()
        iso_weekday = today.isocalendar()[2]
        this_monday = today - timedelta(days=iso_weekday - 1)
        return this_monday - timedelta(days=7)

    # ──────────────────────────────────────────────────────────────────────
    # 1. Weekly Revenue includes POS, SO (Invoice), and Services (Invoice)
    # ──────────────────────────────────────────────────────────────────────

    def test_weekly_revenue_includes_all_sources(self):
        """POS + SO invoice + Service invoice all appear in weekly revenue."""
        from core.models import DocumentStatus, Invoice
        from pos.models import POSSale, POSSaleLine, SaleStatus
        from sales.models import (
            SalesOrder, SalesOrderLine, DeliveryNote, DeliveryLine,
        )
        from services.models import CustomerService, ServiceStatus
        from cashflow.sync import sync_weekly_sales_revenue
        from cashflow.models import CashFlowTransaction
        from django.utils import timezone

        item_a = self._create_item('TA', 'Item A', Decimal('100'), Decimal('200'))
        last_mon = self._last_monday()
        last_tue = last_mon + timedelta(days=1)
        last_wed = last_mon + timedelta(days=2)

        # ── POS Sale (revenue = 200) ─────────────────────────────────────
        # Use noon to avoid timezone-offset pushing date to previous day
        from datetime import datetime as dt
        pos = POSSale.objects.create(
            sale_no='POS-TEST-001',
            register=self.register, shift=self.shift,
            warehouse=self.warehouse, location=self.location,
            status=SaleStatus.POSTED,
            grand_total=Decimal('200'),
            posted_at=timezone.make_aware(
                dt.combine(last_mon, dt.min.time().replace(hour=12))
            ),
            posted_by=self.user,
            created_by=self.user,
        )
        POSSaleLine.objects.create(
            sale=pos, item=item_a, qty=1, unit=self.unit,
            unit_price=Decimal('200'), line_total=Decimal('200'),
        )

        # ── SO → DeliveryNote → Invoice (revenue = 400) ──────────────────
        so = SalesOrder.objects.create(
            document_number='SO-CF-001',
            customer=self.customer, warehouse=self.warehouse,
            order_date=last_tue,
            status=DocumentStatus.POSTED,
            created_by=self.user, posted_by=self.user,
        )
        SalesOrderLine.objects.create(
            sales_order=so, item=item_a, qty_ordered=2, unit=self.unit,
            unit_price=Decimal('200'),
        )
        dn = DeliveryNote.objects.create(
            document_number='DN-CF-001',
            sales_order=so, customer=self.customer, warehouse=self.warehouse,
            delivery_date=last_tue,
            status=DocumentStatus.POSTED,
            created_by=self.user, posted_by=self.user,
        )
        DeliveryLine.objects.create(
            delivery=dn, item=item_a, qty=2, unit=self.unit,
            location=self.location,
        )
        Invoice.objects.create(
            invoice_number='INV-CF-SO-001',
            date=last_tue,
            sales_order=so,
            grand_total=Decimal('400'),
            grand_total_cogs=Decimal('200'),
            created_by=self.user,
        )

        # ── Service → Invoice (revenue = 500) ────────────────────────────
        inv_svc = Invoice.objects.create(
            invoice_number='INV-CF-SVC-001',
            date=last_wed,
            grand_total=Decimal('500'),
            grand_total_cogs=Decimal('50'),
            created_by=self.user,
        )
        CustomerService.objects.create(
            service_number='SVC-CF-001',
            service_name='Test Service',
            customer_name='Walk-in',
            service_date=last_wed,
            completion_date=last_wed,
            status=ServiceStatus.COMPLETED,
            invoice=inv_svc,
            created_by=self.user,
            posted_by=self.user,
        )

        # ── Run sync ─────────────────────────────────────────────────────
        count = sync_weekly_sales_revenue(self.user)
        self.assertGreaterEqual(count, 1)

        from cashflow.sync import _week_source_id
        week_key = _week_source_id(last_mon)
        txn = CashFlowTransaction.objects.filter(
            source_type='WeeklySalesRevenue',
            source_id=week_key,
            is_auto_generated=True,
        ).first()
        self.assertIsNotNone(txn)

        # Expected revenue = POS(200) + SO-Invoice(400) + Svc-Invoice(500) = 1100
        expected_revenue = Decimal('1100.00')
        self.assertEqual(txn.amount, expected_revenue,
                         f'Weekly revenue should be {expected_revenue}, got {txn.amount}')

    # ──────────────────────────────────────────────────────────────────────
    # 2. No duplicate auto entry when a manual entry already exists
    # ──────────────────────────────────────────────────────────────────────

    def test_no_duplicate_procurement_with_manual(self):
        """If a manual CASH_OUT exists for a GRN (same amount+date+ref), skip auto-gen."""
        from core.models import DocumentStatus
        from procurement.models import (
            PurchaseOrder, PurchaseOrderLine,
            GoodsReceipt, GoodsReceiptLine,
        )
        from cashflow.models import CashFlowTransaction, CashFlowCategory, CashFlowType, CashFlowStatus, PaymentMethod
        from cashflow.sync import sync_procurement_cashflow

        item = self._create_item('TB', 'Item B', Decimal('50'), Decimal('100'))

        po = PurchaseOrder.objects.create(
            document_number='PO-CF-001',
            supplier=self.supplier, warehouse=self.warehouse,
            order_date=date.today() - timedelta(days=10),
            status=DocumentStatus.POSTED,
            created_by=self.user,
        )
        PurchaseOrderLine.objects.create(
            purchase_order=po, item=item, qty_ordered=10, unit=self.unit,
            unit_price=Decimal('50'),
        )

        grn = GoodsReceipt.objects.create(
            document_number='GRN-CF-001',
            purchase_order=po, supplier=self.supplier, warehouse=self.warehouse,
            receipt_date=date.today() - timedelta(days=9),
            status=DocumentStatus.POSTED,
            created_by=self.user, posted_by=self.user,
        )
        GoodsReceiptLine.objects.create(
            goods_receipt=grn, item=item, location=self.location,
            qty=10, unit=self.unit,
        )
        # GRN total = 10 × 50 = 500

        # ── Manual entry with exact amount + date + reference_no ─────────
        CashFlowTransaction.objects.create(
            transaction_number='CF-MANUAL-001',
            category=CashFlowCategory.PROCUREMENT,
            flow_type=CashFlowType.CASH_OUT,
            amount=Decimal('500.00'),
            transaction_date=grn.receipt_date,
            payment_method=PaymentMethod.CASH,
            reference_no='GRN-CF-001',
            reason='Manual procurement payment',
            status=CashFlowStatus.APPROVED,
            created_by=self.user,
            is_auto_generated=False,
        )

        grn_count, _ = sync_procurement_cashflow(self.user)
        self.assertEqual(grn_count, 0,
                         'Should not create auto entry when manual entry covers same GRN')

    # ──────────────────────────────────────────────────────────────────────
    # 3. No duplicate auto entry for Expense when manual exists
    # ──────────────────────────────────────────────────────────────────────

    def test_no_duplicate_expense_with_manual(self):
        """If a manual CASH_OUT exists for an expense (same amount+date+ref), skip auto-gen."""
        from core.models import Expense, ExpenseStatus, ExpenseCategory
        from cashflow.models import CashFlowTransaction, CashFlowCategory, CashFlowType, CashFlowStatus, PaymentMethod
        from cashflow.sync import sync_expense_cashflow

        cat = ExpenseCategory.objects.create(name='Test Cat', code='TCAT')
        exp_date = date.today() - timedelta(days=5)
        Expense.objects.create(
            date=exp_date,
            category=cat,
            item_description='Office supplies',
            amount=Decimal('250.00'),
            status=ExpenseStatus.PAID,
            reference_no='REF-EXP-001',
            created_by=self.user,
        )

        CashFlowTransaction.objects.create(
            transaction_number='CF-MANUAL-EXP-001',
            category=CashFlowCategory.EXPENSES,
            flow_type=CashFlowType.CASH_OUT,
            amount=Decimal('250.00'),
            transaction_date=exp_date,
            payment_method=PaymentMethod.CASH,
            reference_no='REF-EXP-001',
            reason='Manual expense payment',
            status=CashFlowStatus.APPROVED,
            created_by=self.user,
            is_auto_generated=False,
        )

        count = sync_expense_cashflow(self.user)
        self.assertEqual(count, 0,
                         'Should not create auto entry when manual entry covers same expense')

    # ──────────────────────────────────────────────────────────────────────
    # 4. Rebuild cleans stale auto entries — no duplication on re-sync
    # ──────────────────────────────────────────────────────────────────────

    def test_sync_rebuilds_auto_entries(self):
        """Running sync twice produces the same count — no duplication."""
        from cashflow.models import CashFlowTransaction
        from cashflow.sync import sync_all

        # Inject a stale auto entry
        CashFlowTransaction.objects.create(
            transaction_number='CF-STALE-001',
            category='PROCUREMENT',
            flow_type='CASH_OUT',
            amount=Decimal('999.99'),
            transaction_date=date.today() - timedelta(days=10),
            payment_method='CASH',
            reason='Stale GRN entry',
            status='PENDING',
            created_by=self.user,
            source_type='GoodsReceipt',
            source_id=99999,
            is_auto_generated=True,
        )

        sync_all(self.user)
        first_count = CashFlowTransaction.objects.filter(is_auto_generated=True).count()

        sync_all(self.user)
        second_count = CashFlowTransaction.objects.filter(is_auto_generated=True).count()

        self.assertEqual(first_count, second_count,
                         f'Sync ran twice but counts differ: {first_count} vs {second_count}')

    # ──────────────────────────────────────────────────────────────────────
    # 5. Current (incomplete) week is NOT synced
    # ──────────────────────────────────────────────────────────────────────

    def test_current_week_skipped(self):
        """Weekly revenue for the current incomplete week should not be created."""
        from pos.models import POSSale, POSSaleLine, SaleStatus
        from cashflow.sync import sync_weekly_sales_revenue, _week_source_id
        from cashflow.models import CashFlowTransaction
        from django.utils import timezone

        item = self._create_item('TC', 'Item C', Decimal('10'), Decimal('50'))
        today = date.today()

        POSSale.objects.create(
            sale_no='POS-CUR-WEEK',
            register=self.register, shift=self.shift,
            warehouse=self.warehouse, location=self.location,
            status=SaleStatus.POSTED,
            grand_total=Decimal('50'),
            posted_at=timezone.now(),
            posted_by=self.user,
            created_by=self.user,
        )

        sync_weekly_sales_revenue(self.user)

        current_key = _week_source_id(today)
        exists = CashFlowTransaction.objects.filter(
            source_type='WeeklySalesRevenue', source_id=current_key,
        ).exists()

        # If today is Sunday the week is complete, so entry SHOULD exist
        if today.isocalendar()[2] == 7:
            self.assertTrue(exists, 'Sunday = complete week, entry should exist')
        else:
            self.assertFalse(exists, 'Current incomplete week should be skipped')

    # ──────────────────────────────────────────────────────────────────────
    # 6. Procurement auto-gen amounts match exact GRN totals
    # ──────────────────────────────────────────────────────────────────────

    def test_procurement_amounts_exact(self):
        """Auto-generated GRN cashflow amount matches PO unit_price × qty."""
        from core.models import DocumentStatus
        from procurement.models import (
            PurchaseOrder, PurchaseOrderLine,
            GoodsReceipt, GoodsReceiptLine,
        )
        from cashflow.models import CashFlowTransaction
        from cashflow.sync import sync_procurement_cashflow

        item = self._create_item('TD', 'Item D', Decimal('75'), Decimal('150'))

        po = PurchaseOrder.objects.create(
            document_number='PO-CF-002',
            supplier=self.supplier, warehouse=self.warehouse,
            order_date=date.today() - timedelta(days=15),
            status=DocumentStatus.POSTED,
            created_by=self.user,
        )
        PurchaseOrderLine.objects.create(
            purchase_order=po, item=item,
            qty_ordered=5, unit=self.unit,
            unit_price=Decimal('80.00'),
        )

        grn = GoodsReceipt.objects.create(
            document_number='GRN-CF-002',
            purchase_order=po, supplier=self.supplier, warehouse=self.warehouse,
            receipt_date=date.today() - timedelta(days=14),
            status=DocumentStatus.POSTED,
            created_by=self.user, posted_by=self.user,
        )
        GoodsReceiptLine.objects.create(
            goods_receipt=grn, item=item, location=self.location,
            qty=5, unit=self.unit,
        )

        sync_procurement_cashflow(self.user)

        txn = CashFlowTransaction.objects.filter(
            source_type='GoodsReceipt', source_id=grn.pk,
            is_auto_generated=True,
        ).first()
        self.assertIsNotNone(txn)
        # 5 × 80 (PO price, not cost_price 75) = 400
        self.assertEqual(txn.amount, Decimal('400.00'),
                         f'GRN cashflow should be 400.00, got {txn.amount}')
        self.assertEqual(txn.flow_type, 'CASH_OUT')
