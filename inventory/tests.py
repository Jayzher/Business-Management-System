"""
Acceptance tests for the inventory posting engine.
Covers: GRN posting, Delivery posting, Transfer posting,
        Adjustment posting, Damaged posting, cancel_document reversal.
"""
from decimal import Decimal
from django.test import TestCase
from django.utils import timezone

from accounts.models import User
from catalog.models import Category, Unit, Item
from partners.models import Supplier, Customer
from warehouses.models import Warehouse, Location
from procurement.models import PurchaseOrder, PurchaseOrderLine, GoodsReceipt, GoodsReceiptLine
from sales.models import SalesOrder, SalesOrderLine, DeliveryNote, DeliveryLine
from inventory.models import (
    StockMove, StockBalance, MoveType,
    StockTransfer, StockTransferLine,
    StockAdjustment, StockAdjustmentLine,
    DamagedReport, DamagedReportLine,
)
from inventory.services import (
    post_goods_receipt, post_delivery, post_transfer,
    post_adjustment, post_damaged_report, cancel_document,
)
from core.models import DocumentStatus


class PostingTestMixin:
    """Shared setUp for posting tests."""

    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='pass123')
        self.category = Category.objects.create(code='CAT', name='Test Category')
        self.unit = Unit.objects.create(name='Piece', abbreviation='pcs')
        self.item = Item.objects.create(
            code='ITEM-001', name='Test Item', item_type='RAW',
            category=self.category, default_unit=self.unit,
        )
        self.warehouse = Warehouse.objects.create(
            code='WH1', name='Test Warehouse', allow_negative_stock=False,
        )
        self.warehouse_neg = Warehouse.objects.create(
            code='WH2', name='Neg Warehouse', allow_negative_stock=True,
        )
        self.location = Location.objects.create(
            warehouse=self.warehouse, code='BIN-1', name='Bin 1',
        )
        self.location2 = Location.objects.create(
            warehouse=self.warehouse, code='BIN-2', name='Bin 2',
        )
        self.location_neg = Location.objects.create(
            warehouse=self.warehouse_neg, code='BIN-N', name='Neg Bin',
        )
        self.supplier = Supplier.objects.create(code='SUP1', name='Test Supplier')
        self.customer = Customer.objects.create(code='CUS1', name='Test Customer')


class PostGoodsReceiptTests(PostingTestMixin, TestCase):

    def _create_grn(self, location=None, qty=Decimal('100')):
        loc = location or self.location
        grn = GoodsReceipt.objects.create(
            document_number=f'GRN-{GoodsReceipt.objects.count()+1:06d}',
            supplier=self.supplier,
            warehouse=loc.warehouse,
            receipt_date=timezone.now().date(),
            created_by=self.user,
        )
        GoodsReceiptLine.objects.create(
            goods_receipt=grn, item=self.item,
            location=loc, qty=qty, unit=self.unit,
        )
        return grn

    def test_post_grn_increases_balance(self):
        grn = self._create_grn(qty=Decimal('50'))
        post_goods_receipt(grn, self.user)

        grn.refresh_from_db()
        self.assertEqual(grn.status, DocumentStatus.POSTED)

        bal = StockBalance.objects.get(item=self.item, location=self.location)
        self.assertEqual(bal.qty_on_hand, Decimal('50'))

        moves = StockMove.objects.filter(reference_type='GoodsReceipt', reference_id=grn.pk)
        self.assertEqual(moves.count(), 1)
        self.assertEqual(moves.first().move_type, MoveType.RECEIVE)

    def test_post_grn_twice_fails(self):
        grn = self._create_grn()
        post_goods_receipt(grn, self.user)
        with self.assertRaises(ValueError):
            post_goods_receipt(grn, self.user)


class PostDeliveryTests(PostingTestMixin, TestCase):

    def _seed_stock(self, location, qty):
        StockBalance.objects.update_or_create(
            item=self.item, location=location,
            defaults={'qty_on_hand': qty, 'qty_reserved': Decimal('0')},
        )

    def _create_delivery(self, location=None, qty=Decimal('10')):
        loc = location or self.location
        dn = DeliveryNote.objects.create(
            document_number=f'DN-{DeliveryNote.objects.count()+1:06d}',
            customer=self.customer,
            warehouse=loc.warehouse,
            delivery_date=timezone.now().date(),
            created_by=self.user,
        )
        DeliveryLine.objects.create(
            delivery=dn, item=self.item,
            location=loc, qty=qty, unit=self.unit,
        )
        return dn

    def test_post_delivery_decreases_balance(self):
        self._seed_stock(self.location, Decimal('100'))
        dn = self._create_delivery(qty=Decimal('30'))
        post_delivery(dn, self.user)

        dn.refresh_from_db()
        self.assertEqual(dn.status, DocumentStatus.POSTED)

        bal = StockBalance.objects.get(item=self.item, location=self.location)
        self.assertEqual(bal.qty_on_hand, Decimal('70'))

    def test_delivery_blocked_if_insufficient_stock(self):
        self._seed_stock(self.location, Decimal('5'))
        dn = self._create_delivery(qty=Decimal('10'))
        with self.assertRaises(ValueError):
            post_delivery(dn, self.user)

    def test_delivery_allowed_if_negative_stock_warehouse(self):
        self._seed_stock(self.location_neg, Decimal('0'))
        dn = self._create_delivery(location=self.location_neg, qty=Decimal('10'))
        post_delivery(dn, self.user)

        bal = StockBalance.objects.get(item=self.item, location=self.location_neg)
        self.assertEqual(bal.qty_on_hand, Decimal('-10'))


class PostTransferTests(PostingTestMixin, TestCase):

    def test_post_transfer(self):
        StockBalance.objects.create(
            item=self.item, location=self.location,
            qty_on_hand=Decimal('50'), qty_reserved=Decimal('0'),
        )
        transfer = StockTransfer.objects.create(
            document_number='TRF-000001',
            from_warehouse=self.warehouse,
            to_warehouse=self.warehouse,
            created_by=self.user,
        )
        StockTransferLine.objects.create(
            transfer=transfer, item=self.item,
            from_location=self.location, to_location=self.location2,
            qty=Decimal('20'), unit=self.unit,
        )
        post_transfer(transfer, self.user)

        bal1 = StockBalance.objects.get(item=self.item, location=self.location)
        bal2 = StockBalance.objects.get(item=self.item, location=self.location2)
        self.assertEqual(bal1.qty_on_hand, Decimal('30'))
        self.assertEqual(bal2.qty_on_hand, Decimal('20'))


class PostAdjustmentTests(PostingTestMixin, TestCase):

    def test_post_adjustment(self):
        StockBalance.objects.create(
            item=self.item, location=self.location,
            qty_on_hand=Decimal('50'), qty_reserved=Decimal('0'),
        )
        adj = StockAdjustment.objects.create(
            document_number='ADJ-000001',
            warehouse=self.warehouse,
            created_by=self.user,
        )
        StockAdjustmentLine.objects.create(
            adjustment=adj, item=self.item, location=self.location,
            qty_counted=Decimal('45'), qty_system=Decimal('50'), unit=self.unit,
        )
        post_adjustment(adj, self.user)

        bal = StockBalance.objects.get(item=self.item, location=self.location)
        self.assertEqual(bal.qty_on_hand, Decimal('45'))


class PostDamagedTests(PostingTestMixin, TestCase):

    def test_post_damaged_report(self):
        StockBalance.objects.create(
            item=self.item, location=self.location,
            qty_on_hand=Decimal('100'), qty_reserved=Decimal('0'),
        )
        report = DamagedReport.objects.create(
            document_number='DMG-000001',
            warehouse=self.warehouse,
            created_by=self.user,
        )
        DamagedReportLine.objects.create(
            report=report, item=self.item, location=self.location,
            qty=Decimal('10'), unit=self.unit, reason='Broken',
        )
        post_damaged_report(report, self.user)

        bal = StockBalance.objects.get(item=self.item, location=self.location)
        self.assertEqual(bal.qty_on_hand, Decimal('90'))


class CancelDocumentTests(PostingTestMixin, TestCase):

    def test_cancel_draft_document(self):
        grn = GoodsReceipt.objects.create(
            document_number='GRN-CANCEL-01',
            supplier=self.supplier, warehouse=self.warehouse,
            receipt_date=timezone.now().date(), created_by=self.user,
        )
        cancel_document(grn, self.user)
        grn.refresh_from_db()
        self.assertEqual(grn.status, DocumentStatus.CANCELLED)
        self.assertEqual(StockMove.objects.filter(reference_type='GoodsReceipt', reference_id=grn.pk).count(), 0)

    def test_cancel_posted_creates_reversals(self):
        StockBalance.objects.create(
            item=self.item, location=self.location,
            qty_on_hand=Decimal('0'), qty_reserved=Decimal('0'),
        )
        grn = GoodsReceipt.objects.create(
            document_number='GRN-CANCEL-02',
            supplier=self.supplier, warehouse=self.warehouse,
            receipt_date=timezone.now().date(), created_by=self.user,
        )
        GoodsReceiptLine.objects.create(
            goods_receipt=grn, item=self.item,
            location=self.location, qty=Decimal('50'), unit=self.unit,
        )
        post_goods_receipt(grn, self.user)

        bal = StockBalance.objects.get(item=self.item, location=self.location)
        self.assertEqual(bal.qty_on_hand, Decimal('50'))

        cancel_document(grn, self.user)
        grn.refresh_from_db()
        self.assertEqual(grn.status, DocumentStatus.CANCELLED)

        bal.refresh_from_db()
        self.assertEqual(bal.qty_on_hand, Decimal('0'))

        # Original + reversal moves
        all_moves = StockMove.objects.filter(reference_type='GoodsReceipt', reference_id=grn.pk)
        self.assertEqual(all_moves.count(), 2)
