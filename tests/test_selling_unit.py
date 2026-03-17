"""
Tests for Item.stock_unit property and selling-unit-normalised inventory posting.

Scenarios:
  1.  stock_unit returns default_unit when selling_unit is None.
  2.  stock_unit returns selling_unit when it is set.
  3.  GRN in roll (procurement unit) → inventory stored in meters (selling_unit).
  4.  GRN in selling_unit directly → inventory unchanged.
  5.  DeliveryNote deducts in selling_unit (converted from doc unit).
  6.  GRN then DN in rolls → net balance in meters is correct.
  7.  StockTransfer in rolls normalises to meters in both locations.
  8.  POS sale in rolls → deducts meters from balance.
  9.  Damaged report in rolls → deducts meters.
 10.  resync Phase 2 re-calculates balance using selling_unit.
 11.  ItemForm clean() rejects selling_unit in different category.
 12.  ItemForm clean() accepts selling_unit in same category as default_unit.
 13.  SalesOrderLineForm clean() validates against item.stock_unit category.
"""
import datetime
from decimal import Decimal
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

User = get_user_model()


# ── shared fixture ────────────────────────────────────────────────────────────

def _setup(cls):
    from catalog.models import (
        Category as ItemCat, Unit, UnitCategory,
        UnitConversion, Item, ItemType,
    )
    from warehouses.models import Warehouse, Location
    from partners.models import Supplier, Customer
    from core.models import DocumentStatus

    cls.user = User.objects.create_superuser('su_u', 'su@t.com', 'pass')
    cls.cat = ItemCat.objects.create(name='SU_Cat', code='SUCAT')
    cls.meter = Unit.objects.create(name='SU_Meter', abbreviation='su_m', category=UnitCategory.LENGTH)
    cls.roll = Unit.objects.create(name='SU_Roll', abbreviation='su_roll', category=UnitCategory.LENGTH)
    # 1 roll = 50 meters
    cls.conv = UnitConversion.objects.create(
        from_unit=cls.roll, to_unit=cls.meter, factor=Decimal('50'))

    cls.pcs = Unit.objects.create(name='SU_Pcs', abbreviation='su_pcs', category=UnitCategory.QUANTITY)

    # Item without selling_unit (stock_unit == default_unit == meter)
    cls.item_no_su = Item.objects.create(
        code='SU_NO_SU', name='NoSellingUnit',
        item_type=ItemType.FINISHED, category=cls.cat,
        default_unit=cls.meter,
        cost_price=Decimal('10'), selling_price=Decimal('20'),
    )
    # Item WITH selling_unit=meter, default_unit=roll (procurement in rolls, sells in meters)
    cls.item_su = Item.objects.create(
        code='SU_WITH_SU', name='WithSellingUnit',
        item_type=ItemType.FINISHED, category=cls.cat,
        default_unit=cls.roll,
        selling_unit=cls.meter,
        cost_price=Decimal('5'), selling_price=Decimal('10'),
    )

    cls.wh = Warehouse.objects.create(name='SU_WH', code='SUWH')
    cls.loc = Location.objects.create(name='SU_Loc', code='SULOC', warehouse=cls.wh)
    cls.loc2 = Location.objects.create(name='SU_Loc2', code='SULOC2', warehouse=cls.wh)
    cls.supplier = Supplier.objects.create(name='SU_Sup', code='SUSUP')
    cls.customer = Customer.objects.create(name='SU_Cust', code='SUCUS')


# ── helpers ───────────────────────────────────────────────────────────────────

def _post_grn(cls, item, qty, unit, location=None):
    from procurement.models import (
        GoodsReceipt, GoodsReceiptLine, PurchaseOrder, PurchaseOrderLine,
    )
    from inventory.services import post_goods_receipt
    from core.models import DocumentStatus
    loc = location or cls.loc
    n = GoodsReceipt.objects.count() + 1
    po = PurchaseOrder.objects.create(
        document_number=f'PO-SU-{n:04d}',
        supplier=cls.supplier, warehouse=cls.wh,
        order_date=datetime.date.today(), created_by=cls.user,
        status=DocumentStatus.APPROVED,
    )
    PurchaseOrderLine.objects.create(
        purchase_order=po, item=item,
        qty_ordered=qty, unit=unit, unit_price=Decimal('5'),
    )
    grn = GoodsReceipt.objects.create(
        document_number=f'GRN-SU-{n:04d}',
        purchase_order=po, supplier=cls.supplier,
        warehouse=cls.wh, receipt_date=datetime.date.today(),
        created_by=cls.user,
    )
    GoodsReceiptLine.objects.create(
        goods_receipt=grn, item=item, location=loc, qty=qty, unit=unit,
    )
    post_goods_receipt(grn, cls.user)
    return grn


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


# ── Tests ─────────────────────────────────────────────────────────────────────

class StockUnitPropertyTest(TestCase):
    """stock_unit property returns correct unit."""

    @classmethod
    def setUpTestData(cls):
        _setup(cls)

    def test_no_selling_unit_returns_default_unit(self):
        self.assertIsNone(self.item_no_su.selling_unit_id)
        self.assertEqual(self.item_no_su.stock_unit, self.item_no_su.default_unit)
        self.assertEqual(self.item_no_su.stock_unit, self.meter)

    def test_with_selling_unit_returns_selling_unit(self):
        self.assertEqual(self.item_su.default_unit, self.roll)
        self.assertEqual(self.item_su.selling_unit, self.meter)
        self.assertEqual(self.item_su.stock_unit, self.meter)


class GRNSellingUnitTest(TestCase):
    """GRN posted in procurement unit → balance stored in selling_unit."""

    @classmethod
    def setUpTestData(cls):
        _setup(cls)

    def test_grn_3_rolls_stores_150_meters(self):
        # item_su: default_unit=roll, selling_unit=meter (1 roll=50m)
        _post_grn(self, self.item_su, Decimal('3'), self.roll)
        # Expected: 3 rolls × 50 = 150 meters
        self.assertEqual(_get_balance(self.item_su, self.loc), Decimal('150'))

    def test_grn_in_selling_unit_stores_directly(self):
        # Receive in meters directly (no conversion needed)
        _post_grn(self, self.item_su, Decimal('100'), self.meter)
        self.assertEqual(_get_balance(self.item_su, self.loc), Decimal('100'))

    def test_item_no_selling_unit_uses_default(self):
        # item_no_su: default_unit=meter, no selling_unit
        _post_grn(self, self.item_no_su, Decimal('200'), self.meter)
        self.assertEqual(_get_balance(self.item_no_su, self.loc), Decimal('200'))

    def test_stockmove_unit_is_selling_unit(self):
        from inventory.models import StockMove
        _post_grn(self, self.item_su, Decimal('2'), self.roll)
        move = StockMove.objects.filter(
            reference_type='GoodsReceipt', item=self.item_su
        ).first()
        self.assertIsNotNone(move)
        self.assertEqual(move.unit, self.meter)
        self.assertEqual(move.qty, Decimal('100'))  # 2 × 50


class DeliveryNoteSellingUnitTest(TestCase):
    """DN deducts balance using selling_unit conversion."""

    @classmethod
    def setUpTestData(cls):
        _setup(cls)

    def test_dn_2_rolls_deducts_100_meters(self):
        from sales.models import DeliveryNote, DeliveryLine
        from inventory.services import post_delivery
        from core.models import DocumentStatus
        from inventory.models import StockBalance

        # Seed 200m balance
        StockBalance.objects.create(
            item=self.item_su, location=self.loc,
            qty_on_hand=Decimal('200'), qty_reserved=Decimal('0'),
        )
        dn = DeliveryNote.objects.create(
            document_number='DN-SU-001',
            customer=self.customer, warehouse=self.wh,
            delivery_date=datetime.date.today(), created_by=self.user,
        )
        DeliveryLine.objects.create(
            delivery=dn, item=self.item_su, location=self.loc,
            qty=Decimal('2'), unit=self.roll,
        )
        post_delivery(dn, self.user)
        # 200 - 2*50 = 100
        self.assertEqual(_get_balance(self.item_su, self.loc), Decimal('100'))


class GRNthenDNSellingUnitTest(TestCase):
    """GRN 4 rolls then DN 1 roll → net 150 meters."""

    @classmethod
    def setUpTestData(cls):
        _setup(cls)

    def test_net_balance_in_meters(self):
        from sales.models import DeliveryNote, DeliveryLine
        from inventory.services import post_delivery
        from core.models import DocumentStatus

        _post_grn(self, self.item_su, Decimal('4'), self.roll)   # +200 m
        dn = DeliveryNote.objects.create(
            document_number='DN-SU-002',
            customer=self.customer, warehouse=self.wh,
            delivery_date=datetime.date.today(), created_by=self.user,
        )
        DeliveryLine.objects.create(
            delivery=dn, item=self.item_su, location=self.loc,
            qty=Decimal('1'), unit=self.roll,
        )
        post_delivery(dn, self.user)   # -50 m
        self.assertEqual(_get_balance(self.item_su, self.loc), Decimal('150'))


class TransferSellingUnitTest(TestCase):
    """StockTransfer in rolls normalises to meters in both locations."""

    @classmethod
    def setUpTestData(cls):
        _setup(cls)

    def test_transfer_2_rolls_moves_100_meters(self):
        from inventory.models import StockTransfer, StockTransferLine, StockBalance
        from inventory.services import post_transfer
        from core.models import DocumentStatus

        StockBalance.objects.create(
            item=self.item_su, location=self.loc,
            qty_on_hand=Decimal('200'), qty_reserved=Decimal('0'),
        )
        tr = StockTransfer.objects.create(
            document_number='TR-SU-001',
            from_warehouse=self.wh, to_warehouse=self.wh,
            created_by=self.user,
        )
        StockTransferLine.objects.create(
            transfer=tr, item=self.item_su,
            from_location=self.loc, to_location=self.loc2,
            qty=Decimal('2'), unit=self.roll,
        )
        post_transfer(tr, self.user)
        self.assertEqual(_get_balance(self.item_su, self.loc), Decimal('100'))
        self.assertEqual(_get_balance(self.item_su, self.loc2), Decimal('100'))


class DamagedReportSellingUnitTest(TestCase):
    """Damaged report in rolls → deducts meters."""

    @classmethod
    def setUpTestData(cls):
        _setup(cls)

    def test_damaged_1_roll_deducts_50_meters(self):
        from inventory.models import DamagedReport, DamagedReportLine, StockBalance
        from inventory.services import post_damaged_report
        from core.models import DocumentStatus

        StockBalance.objects.create(
            item=self.item_su, location=self.loc,
            qty_on_hand=Decimal('200'), qty_reserved=Decimal('0'),
        )
        dr = DamagedReport.objects.create(
            document_number='DAM-SU-001', warehouse=self.wh,
            created_by=self.user,
        )
        DamagedReportLine.objects.create(
            report=dr, item=self.item_su, location=self.loc,
            qty=Decimal('1'), unit=self.roll,
        )
        post_damaged_report(dr, self.user)
        self.assertEqual(_get_balance(self.item_su, self.loc), Decimal('150'))


class ResyncSellingUnitTest(TestCase):
    """Resync Phase 2 recalculates balance using selling_unit."""

    @classmethod
    def setUpTestData(cls):
        _setup(cls)

    def test_resync_uses_selling_unit(self):
        from inventory.models import StockBalance

        # GRN: 3 rolls (should produce 150 m balance)
        _post_grn(self, self.item_su, Decimal('3'), self.roll)

        # Corrupt balance to simulate legacy state (raw 3 rolls)
        StockBalance.objects.filter(item=self.item_su, location=self.loc).update(
            qty_on_hand=Decimal('3')
        )
        self.assertEqual(_get_balance(self.item_su, self.loc), Decimal('3'))  # confirm corrupt

        _call_resync('--phase', '2', '--apply')

        # Phase 2 replays GRN line: 3 rolls × 50 = 150 meters
        self.assertEqual(_get_balance(self.item_su, self.loc), Decimal('150'))


class ItemFormSellingUnitValidationTest(TestCase):
    """ItemForm.clean() rejects cross-category selling_unit."""

    @classmethod
    def setUpTestData(cls):
        _setup(cls)

    def test_rejects_different_category(self):
        from catalog.forms import ItemForm

        form = ItemForm(data={
            'code': 'SU_FORM_BAD',
            'name': 'Bad Selling Unit',
            'item_type': 'FINISHED',
            'category': self.cat.pk,
            'default_unit': self.meter.pk,
            'selling_unit': self.pcs.pk,  # QUANTITY ≠ LENGTH → invalid
            'cost_price': '10',
            'selling_price': '20',
            'minimum_stock': '0',
            'maximum_stock': '0',
            'reorder_point': '0',
        })
        self.assertFalse(form.is_valid())
        self.assertIn('selling_unit', form.errors)

    def test_accepts_same_category(self):
        from catalog.forms import ItemForm

        form = ItemForm(data={
            'code': 'SU_FORM_OK',
            'name': 'Good Selling Unit',
            'item_type': 'FINISHED',
            'category': self.cat.pk,
            'default_unit': self.roll.pk,
            'selling_unit': self.meter.pk,  # same LENGTH category → valid
            'cost_price': '10',
            'selling_price': '20',
            'minimum_stock': '0',
            'maximum_stock': '0',
            'reorder_point': '0',
        })
        self.assertTrue(form.is_valid(), form.errors)

    def test_accepts_no_selling_unit(self):
        from catalog.forms import ItemForm

        form = ItemForm(data={
            'code': 'SU_FORM_NONE',
            'name': 'No Selling Unit',
            'item_type': 'FINISHED',
            'category': self.cat.pk,
            'default_unit': self.meter.pk,
            'selling_unit': '',
            'cost_price': '10',
            'selling_price': '20',
            'minimum_stock': '0',
            'maximum_stock': '0',
            'reorder_point': '0',
        })
        self.assertTrue(form.is_valid(), form.errors)


class SOLineFormStockUnitValidationTest(TestCase):
    """SalesOrderLineForm validates unit category against item.stock_unit."""

    @classmethod
    def setUpTestData(cls):
        _setup(cls)
        from catalog.models import Item, ItemType, Unit, UnitCategory
        from warehouses.models import Warehouse
        from partners.models import Customer
        from sales.models import SalesOrder
        from core.models import DocumentStatus

        cls.wh2 = Warehouse.objects.create(name='SU_WH2', code='SUWH2')
        cls.so = SalesOrder.objects.create(
            document_number='SO-SU-001',
            customer=cls.customer, warehouse=cls.wh,
            order_date=datetime.date.today(), created_by=cls.user,
        )

    def test_rejects_unit_incompatible_with_stock_unit(self):
        from sales.forms import SalesOrderLineForm

        # item_su.stock_unit = meter (LENGTH); pcs is QUANTITY → invalid
        form = SalesOrderLineForm(data={
            'item': self.item_su.pk,
            'qty_ordered': '5',
            'unit': self.pcs.pk,
            'unit_price': '10',
            'discount_type': 'PERCENT',
            'discount_value': '0',
        })
        self.assertFalse(form.is_valid())
        self.assertIn('unit', form.errors)

    def test_accepts_unit_in_same_category_as_stock_unit(self):
        from sales.forms import SalesOrderLineForm

        # item_su.stock_unit = meter (LENGTH); roll is also LENGTH → valid
        form = SalesOrderLineForm(data={
            'item': self.item_su.pk,
            'qty_ordered': '2',
            'unit': self.roll.pk,
            'unit_price': '10',
            'discount_type': 'PERCENT',
            'discount_value': '0',
        })
        self.assertTrue(form.is_valid(), form.errors)
