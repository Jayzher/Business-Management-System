"""
Tests for inventory/management/commands/resync_inventory.py

Scenarios covered:
  1.  Phase 2 dry-run: StockBalance unchanged.
  2.  Phase 2 --apply: single-item GRN → correct balance from document line.
  3.  Phase 2 --apply: GRN in boxes (1 box=20 pcs), stock balance = 60 pcs.
  4.  Phase 2 --apply: GRN then DN in boxes → net balance correct.
  5.  Phase 2 --apply: POS sale in boxes → balance deducted correctly.
  6.  Phase 2 --apply: Stock Transfer (box → same item pcs) → from/to locations correct.
  7.  Phase 2 --apply: damaged report in boxes → balance deducted.
  8.  Phase 2 --apply: multiple docs, cumulative balance is accurate.
  9.  Phase 1 --apply: existing StockMove with wrong qty gets corrected.
  10. Full cycle: wrong move + wrong balance → both corrected.
"""
import datetime
from decimal import Decimal
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

User = get_user_model()


# ── test fixtures ─────────────────────────────────────────────────────────────

def _setup_base(cls):
    from catalog.models import Category as ItemCat, Unit, UnitCategory, UnitConversion, Item, ItemType
    from warehouses.models import Warehouse, Location
    from partners.models import Supplier, Customer
    from core.models import DocumentStatus

    cls.user = User.objects.create_superuser('ri_u', 'ri@t.com', 'pass')

    cls.cat_items = ItemCat.objects.create(name='RI_Cat', code='RICAT')
    cls.pcs = Unit.objects.create(name='RI_Piece', abbreviation='ripcs', category=UnitCategory.QUANTITY)
    cls.box = Unit.objects.create(name='RI_Box', abbreviation='ribx', category=UnitCategory.QUANTITY)
    # 1 box = 20 pcs
    cls.conv = UnitConversion.objects.create(
        from_unit=cls.box, to_unit=cls.pcs, factor=Decimal('20'))

    cls.item = Item.objects.create(
        code='RI_ITM', name='ResyncItem',
        item_type=ItemType.FINISHED,
        category=cls.cat_items,
        default_unit=cls.pcs,
        cost_price=Decimal('10'),
        selling_price=Decimal('20'),
    )

    cls.wh = Warehouse.objects.create(name='RI_WH', code='RIWH')
    cls.loc1 = Location.objects.create(name='RI_Loc1', code='RILOC1', warehouse=cls.wh)
    cls.loc2 = Location.objects.create(name='RI_Loc2', code='RILOC2', warehouse=cls.wh)
    cls.supplier = Supplier.objects.create(name='RI_Sup', code='RISUP')
    cls.customer = Customer.objects.create(name='RI_Cust', code='RICUS')


def _make_posted_grn(cls, qty, unit, location=None, doc_no=None):
    from procurement.models import GoodsReceipt, GoodsReceiptLine, PurchaseOrder, PurchaseOrderLine
    from core.models import DocumentStatus
    loc = location or cls.loc1
    n = GoodsReceipt.objects.count() + 1
    po = PurchaseOrder.objects.create(
        document_number=f'PO-RI-{n:04d}',
        supplier=cls.supplier, warehouse=cls.wh,
        order_date=datetime.date.today(), created_by=cls.user,
        status=DocumentStatus.APPROVED,
    )
    PurchaseOrderLine.objects.create(
        purchase_order=po, item=cls.item,
        qty_ordered=qty, unit=unit, unit_price=Decimal('10'),
    )
    grn = GoodsReceipt.objects.create(
        document_number=doc_no or f'GRN-RI-{n:04d}',
        purchase_order=po, supplier=cls.supplier,
        warehouse=cls.wh, receipt_date=datetime.date.today(),
        created_by=cls.user, status=DocumentStatus.POSTED,
        posted_by=cls.user,
    )
    GoodsReceiptLine.objects.create(
        goods_receipt=grn, item=cls.item,
        location=loc, qty=qty, unit=unit,
    )
    return grn


def _make_posted_dn(cls, qty, unit, location=None, doc_no=None):
    from sales.models import DeliveryNote, DeliveryLine
    from core.models import DocumentStatus
    loc = location or cls.loc1
    n = DeliveryNote.objects.count() + 1
    dn = DeliveryNote.objects.create(
        document_number=doc_no or f'DN-RI-{n:04d}',
        customer=cls.customer, warehouse=cls.wh,
        delivery_date=datetime.date.today(), created_by=cls.user,
        status=DocumentStatus.POSTED, posted_by=cls.user,
    )
    DeliveryLine.objects.create(
        delivery=dn, item=cls.item, location=loc, qty=qty, unit=unit,
    )
    return dn


def _set_balance(item, location, qty):
    from inventory.models import StockBalance
    StockBalance.objects.update_or_create(
        item=item, location=location,
        defaults={'qty_on_hand': qty, 'qty_reserved': Decimal('0')},
    )


def _get_balance(item, location):
    from inventory.models import StockBalance
    try:
        return StockBalance.objects.get(item=item, location=location).qty_on_hand
    except StockBalance.DoesNotExist:
        return Decimal('0')


def _call_resync(*args):
    out = StringIO()
    call_command('resync_inventory', *args, stdout=out)
    return out.getvalue()


# ── test classes ──────────────────────────────────────────────────────────────

class ResyncDryRunTest(TestCase):
    """Phase 2 dry-run must not change any balance."""

    @classmethod
    def setUpTestData(cls):
        _setup_base(cls)

    def test_dry_run_leaves_balance_unchanged(self):
        _make_posted_grn(self, Decimal('3'), self.box)  # correct would be 60 pcs
        _set_balance(self.item, self.loc1, Decimal('999'))  # intentionally wrong

        _call_resync('--phase', '2')   # no --apply

        self.assertEqual(_get_balance(self.item, self.loc1), Decimal('999'))


class ResyncPhase2BasicTest(TestCase):
    """GRN in pcs (no conversion needed) → balance = exact qty."""

    @classmethod
    def setUpTestData(cls):
        _setup_base(cls)

    def test_grn_same_unit_sets_correct_balance(self):
        _make_posted_grn(self, Decimal('50'), self.pcs)
        _call_resync('--phase', '2', '--apply')
        self.assertEqual(_get_balance(self.item, self.loc1), Decimal('50'))


class ResyncPhase2BoxConversionTest(TestCase):
    """GRN in boxes → balance in pcs via convert_to_base_unit."""

    @classmethod
    def setUpTestData(cls):
        _setup_base(cls)

    def test_grn_3_boxes_gives_60_pcs(self):
        _make_posted_grn(self, Decimal('3'), self.box)  # 3 × 20 = 60
        _call_resync('--phase', '2', '--apply')
        self.assertEqual(_get_balance(self.item, self.loc1), Decimal('60'))


class ResyncPhase2GRNthenDNTest(TestCase):
    """GRN 5 boxes (=100 pcs) then DN 2 boxes (=40 pcs) → 60 pcs net."""

    @classmethod
    def setUpTestData(cls):
        _setup_base(cls)

    def test_grn_minus_dn_in_boxes(self):
        _make_posted_grn(self, Decimal('5'), self.box)  # +100 pcs
        _make_posted_dn(self, Decimal('2'), self.box)   # -40 pcs
        _call_resync('--phase', '2', '--apply')
        self.assertEqual(_get_balance(self.item, self.loc1), Decimal('60'))


class ResyncPhase2POSSaleTest(TestCase):
    """POS sale in boxes deducts correct pcs from balance."""

    @classmethod
    def setUpTestData(cls):
        _setup_base(cls)
        from pos.models import POSRegister, POSShift, POSSale, POSSaleLine, SaleStatus, ShiftStatus
        from catalog.models import Unit, UnitCategory
        cls.reg = POSRegister.objects.create(
            name='RI_POS', warehouse=cls.wh, default_location=cls.loc1)
        cls.shift = POSShift.objects.create(
            register=cls.reg, opened_by=cls.user,
            opened_at=datetime.datetime(2025, 1, 1, 8, 0),
            opening_cash=Decimal('0'), status=ShiftStatus.OPEN,
        )
        cls.sale = POSSale.objects.create(
            sale_no='POS-RI-001', register=cls.reg, shift=cls.shift,
            warehouse=cls.wh, location=cls.loc1, status=SaleStatus.POSTED,
            grand_total=Decimal('100'), subtotal=Decimal('100'),
            created_by=cls.user, posted_by=cls.user,
            posted_at=datetime.datetime(2025, 1, 1, 9, 0),
        )
        POSSaleLine.objects.create(
            sale=cls.sale, item=cls.item, qty=Decimal('2'), unit=cls.box,
            unit_price=Decimal('50'), line_total=Decimal('100'),
        )

    def test_pos_sale_2_boxes_deducts_40_pcs(self):
        # Start with 100 pcs on hand
        _set_balance(self.item, self.loc1, Decimal('100'))
        # Resync recalculates from documents only — POS sale = -2 boxes = -40 pcs
        # Since there's no GRN in this test, net from documents = -40
        _call_resync('--phase', '2', '--apply')
        self.assertEqual(_get_balance(self.item, self.loc1), Decimal('-40'))


class ResyncPhase2TransferTest(TestCase):
    """Stock Transfer in boxes: deducts from loc1, adds to loc2."""

    @classmethod
    def setUpTestData(cls):
        _setup_base(cls)
        from inventory.models import StockTransfer, StockTransferLine
        from core.models import DocumentStatus
        tr = StockTransfer.objects.create(
            document_number='TR-RI-001',
            from_warehouse=cls.wh, to_warehouse=cls.wh,
            created_by=cls.user, status=DocumentStatus.POSTED,
            posted_by=cls.user,
        )
        StockTransferLine.objects.create(
            transfer=tr, item=cls.item,
            from_location=cls.loc1, to_location=cls.loc2,
            qty=Decimal('2'), unit=cls.box,  # 2 × 20 = 40 pcs
        )

    def test_transfer_2_boxes_moves_40_pcs(self):
        _call_resync('--phase', '2', '--apply')
        # loc1: -40, loc2: +40
        self.assertEqual(_get_balance(self.item, self.loc1), Decimal('-40'))
        self.assertEqual(_get_balance(self.item, self.loc2), Decimal('40'))


class ResyncPhase2DamagedTest(TestCase):
    """Damaged report in boxes deducts correct pcs."""

    @classmethod
    def setUpTestData(cls):
        _setup_base(cls)
        from inventory.models import DamagedReport, DamagedReportLine
        from core.models import DocumentStatus
        dr = DamagedReport.objects.create(
            document_number='DAM-RI-001', warehouse=cls.wh,
            created_by=cls.user, status=DocumentStatus.POSTED,
            posted_by=cls.user,
        )
        DamagedReportLine.objects.create(
            report=dr, item=cls.item, location=cls.loc1,
            qty=Decimal('1'), unit=cls.box,  # 1 × 20 = 20 pcs
        )

    def test_damaged_1_box_deducts_20_pcs(self):
        _call_resync('--phase', '2', '--apply')
        self.assertEqual(_get_balance(self.item, self.loc1), Decimal('-20'))


class ResyncPhase2CumulativeTest(TestCase):
    """GRN + DN + Damaged all in boxes → correct cumulative balance."""

    @classmethod
    def setUpTestData(cls):
        _setup_base(cls)

    def test_cumulative_balance(self):
        # +5 boxes = +100 pcs
        _make_posted_grn(self, Decimal('5'), self.box)
        # -1 box = -20 pcs
        _make_posted_dn(self, Decimal('1'), self.box)
        # -1 box damaged = -20 pcs
        from inventory.models import DamagedReport, DamagedReportLine
        from core.models import DocumentStatus
        dr = DamagedReport.objects.create(
            document_number='DAM-RI-CUM', warehouse=self.wh,
            created_by=self.user, status=DocumentStatus.POSTED,
            posted_by=self.user,
        )
        DamagedReportLine.objects.create(
            report=dr, item=self.item, location=self.loc1,
            qty=Decimal('1'), unit=self.box,
        )
        _call_resync('--phase', '2', '--apply')
        # 100 - 20 - 20 = 60
        self.assertEqual(_get_balance(self.item, self.loc1), Decimal('60'))


class ResyncPhase1FixMovesTest(TestCase):
    """Phase 1 corrects StockMove.qty from wrong raw qty to base-unit qty."""

    @classmethod
    def setUpTestData(cls):
        _setup_base(cls)

    def test_phase1_corrects_wrong_move_qty(self):
        from inventory.models import StockMove, MoveType
        from inventory.services import post_goods_receipt
        from procurement.models import GoodsReceipt, GoodsReceiptLine, PurchaseOrder, PurchaseOrderLine
        from core.models import DocumentStatus

        # Build a DRAFT GRN and post it — this creates a StockMove (currently
        # with the new correct logic: 60 pcs).  Then corrupt the move to
        # simulate what legacy code used to store (raw 3 boxes).
        po = PurchaseOrder.objects.create(
            document_number='PO-P1-001',
            supplier=self.supplier, warehouse=self.wh,
            order_date=datetime.date.today(), created_by=self.user,
            status=DocumentStatus.APPROVED,
        )
        PurchaseOrderLine.objects.create(
            purchase_order=po, item=self.item,
            qty_ordered=Decimal('3'), unit=self.box, unit_price=Decimal('10'),
        )
        grn = GoodsReceipt.objects.create(
            document_number='GRN-P1-001',
            purchase_order=po, supplier=self.supplier,
            warehouse=self.wh, receipt_date=datetime.date.today(),
            created_by=self.user,
        )
        GoodsReceiptLine.objects.create(
            goods_receipt=grn, item=self.item,
            location=self.loc1, qty=Decimal('3'), unit=self.box,
        )
        post_goods_receipt(grn, self.user)  # creates StockMove (correct: 60 pcs)

        # Corrupt the StockMove to simulate pre-fix legacy state (raw 3 boxes)
        move = StockMove.objects.filter(
            reference_type='GoodsReceipt', reference_id=grn.pk,
        ).first()
        self.assertIsNotNone(move, 'post_goods_receipt must create a StockMove')
        move.qty = Decimal('3')
        move.unit = self.box
        move.save(update_fields=['qty', 'unit_id'])

        _call_resync('--phase', '1', '--apply')

        move.refresh_from_db()
        self.assertEqual(move.qty, Decimal('60'))
        self.assertEqual(move.unit_id, self.pcs.pk)


class ResyncPhase1BackfillPONoGRNLinkTest(TestCase):
    """Phase 1 creates a PO for posted GRNs that have no purchase_order link."""

    @classmethod
    def setUpTestData(cls):
        _setup_base(cls)

    def test_phase1_creates_po_for_posted_grn_without_purchase_order(self):
        from procurement.models import GoodsReceipt, GoodsReceiptLine, PurchaseOrder
        from core.models import DocumentStatus

        grn = GoodsReceipt.objects.create(
            document_number='GRN-NOPO-001',
            supplier=self.supplier,
            warehouse=self.wh,
            receipt_date=datetime.date.today(),
            created_by=self.user,
            status=DocumentStatus.POSTED,
            posted_by=self.user,
        )
        GoodsReceiptLine.objects.create(
            goods_receipt=grn,
            item=self.item,
            location=self.loc1,
            qty=Decimal('3'),
            unit=self.box,
        )

        self.assertEqual(PurchaseOrder.objects.count(), 0)
        self.assertIsNone(grn.purchase_order_id)

        _call_resync('--phase', '1', '--apply')

        grn.refresh_from_db()
        self.assertIsNotNone(grn.purchase_order_id)
        self.assertEqual(PurchaseOrder.objects.count(), 1)
        self.assertEqual(grn.purchase_order.supplier_id, self.supplier.id)
        self.assertEqual(grn.purchase_order.warehouse_id, self.wh.id)
        self.assertEqual(grn.purchase_order.lines.count(), 1)

        po_line = grn.purchase_order.lines.first()
        self.assertEqual(po_line.item_id, self.item.id)
        self.assertEqual(po_line.qty_ordered, Decimal('3'))
        self.assertEqual(po_line.qty_received, Decimal('3'))
        self.assertEqual(po_line.unit_id, self.box.id)


class ResyncFullCycleTest(TestCase):
    """Phase 1 + Phase 2 together: wrong move qty AND wrong balance both fixed."""

    @classmethod
    def setUpTestData(cls):
        _setup_base(cls)

    def test_full_resync_fixes_move_and_balance(self):
        from inventory.models import StockMove
        from inventory.services import post_goods_receipt
        from procurement.models import GoodsReceipt, GoodsReceiptLine, PurchaseOrder, PurchaseOrderLine
        from core.models import DocumentStatus

        # Create and post GRN (correct logic creates StockMove with 80 pcs)
        po = PurchaseOrder.objects.create(
            document_number='PO-FC-001',
            supplier=self.supplier, warehouse=self.wh,
            order_date=datetime.date.today(), created_by=self.user,
            status=DocumentStatus.APPROVED,
        )
        PurchaseOrderLine.objects.create(
            purchase_order=po, item=self.item,
            qty_ordered=Decimal('4'), unit=self.box, unit_price=Decimal('10'),
        )
        grn = GoodsReceipt.objects.create(
            document_number='GRN-FC-001',
            purchase_order=po, supplier=self.supplier,
            warehouse=self.wh, receipt_date=datetime.date.today(),
            created_by=self.user,
        )
        GoodsReceiptLine.objects.create(
            goods_receipt=grn, item=self.item,
            location=self.loc1, qty=Decimal('4'), unit=self.box,
        )
        post_goods_receipt(grn, self.user)   # StockMove: 80 pcs, balance: 80

        # Corrupt both to simulate pre-fix legacy state
        move = StockMove.objects.filter(
            reference_type='GoodsReceipt', reference_id=grn.pk).first()
        self.assertIsNotNone(move)
        move.qty = Decimal('4')
        move.unit = self.box
        move.save(update_fields=['qty', 'unit_id'])
        _set_balance(self.item, self.loc1, Decimal('4'))  # wrong raw balance

        _call_resync('--apply')   # both phases

        # Move corrected by Phase 1
        move.refresh_from_db()
        self.assertEqual(move.qty, Decimal('80'))
        self.assertEqual(move.unit_id, self.pcs.pk)

        # Balance corrected by Phase 2 (reads from GRN line: 4 boxes × 20 = 80)
        self.assertEqual(_get_balance(self.item, self.loc1), Decimal('80'))


class ResyncIdempotentTest(TestCase):
    """Running resync twice produces the same result."""

    @classmethod
    def setUpTestData(cls):
        _setup_base(cls)

    def test_idempotent(self):
        _make_posted_grn(self, Decimal('3'), self.box)   # 60 pcs

        _call_resync('--phase', '2', '--apply')
        bal_first = _get_balance(self.item, self.loc1)

        _call_resync('--phase', '2', '--apply')
        bal_second = _get_balance(self.item, self.loc1)

        self.assertEqual(bal_first, Decimal('60'))
        self.assertEqual(bal_second, Decimal('60'))
