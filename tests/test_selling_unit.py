"""
Tests for Item.stock_unit property and default-unit-based inventory posting.

stock_unit always returns default_unit (the procurement/base unit).
selling_unit is used only at the sales/invoice layer and never affects
how stock quantities are stored.

Scenarios:
  1.  stock_unit returns default_unit when selling_unit is None.
  2.  stock_unit returns default_unit even when selling_unit is set.
  3.  GRN in roll (default_unit) → inventory stored in rolls.
  4.  GRN in meters (non-default unit) → converted to rolls for storage.
  5.  DeliveryNote deducts in default_unit (converted from doc unit).
  6.  GRN then DN in rolls → net balance in rolls is correct.
  7.  StockTransfer in meters normalises to rolls in both locations.
  8.  Damaged report in meters → deducts rolls.
  9.  resync Phase 2 re-calculates balance using default_unit.
 10.  ItemForm clean() rejects selling_unit in different category.
 11.  ItemForm clean() accepts selling_unit in same category as default_unit.
 12.  SalesOrderLineForm clean() validates against item.stock_unit category.
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
    # Item WITH selling_unit=meter, default_unit=roll
    # stock_unit is always default_unit=roll (selling_unit is for sales layer only)
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
    """stock_unit property always returns default_unit."""

    @classmethod
    def setUpTestData(cls):
        _setup(cls)

    def test_no_selling_unit_returns_default_unit(self):
        self.assertIsNone(self.item_no_su.selling_unit_id)
        self.assertEqual(self.item_no_su.stock_unit, self.item_no_su.default_unit)
        self.assertEqual(self.item_no_su.stock_unit, self.meter)

    def test_with_selling_unit_still_returns_default_unit(self):
        """stock_unit ignores selling_unit and always returns default_unit."""
        self.assertEqual(self.item_su.default_unit, self.roll)
        self.assertEqual(self.item_su.selling_unit, self.meter)
        # stock_unit == default_unit == roll (NOT meter)
        self.assertEqual(self.item_su.stock_unit, self.roll)


class GRNDefaultUnitTest(TestCase):
    """GRN posted → balance stored in default_unit (procurement unit)."""

    @classmethod
    def setUpTestData(cls):
        _setup(cls)

    def test_grn_3_rolls_stores_3_rolls(self):
        # item_su: default_unit=roll, selling_unit=meter
        # stock_unit=roll → no conversion, stored as 3 rolls
        _post_grn(self, self.item_su, Decimal('3'), self.roll)
        self.assertEqual(_get_balance(self.item_su, self.loc), Decimal('3'))

    def test_grn_in_meters_converts_to_rolls(self):
        # Receive 100 meters → converted to rolls: 100 / 50 = 2 rolls
        _post_grn(self, self.item_su, Decimal('100'), self.meter)
        self.assertEqual(_get_balance(self.item_su, self.loc), Decimal('2'))

    def test_item_no_selling_unit_uses_default(self):
        # item_no_su: default_unit=meter, no selling_unit
        _post_grn(self, self.item_no_su, Decimal('200'), self.meter)
        self.assertEqual(_get_balance(self.item_no_su, self.loc), Decimal('200'))

    def test_stockmove_unit_is_default_unit(self):
        from inventory.models import StockMove
        _post_grn(self, self.item_su, Decimal('2'), self.roll)
        move = StockMove.objects.filter(
            reference_type='GoodsReceipt', item=self.item_su
        ).first()
        self.assertIsNotNone(move)
        # StockMove stored in default_unit=roll
        self.assertEqual(move.unit, self.roll)
        self.assertEqual(move.qty, Decimal('2'))


class DeliveryNoteDefaultUnitTest(TestCase):
    """DN deducts balance using default_unit conversion."""

    @classmethod
    def setUpTestData(cls):
        _setup(cls)

    def test_dn_in_meters_deducts_rolls(self):
        from sales.models import DeliveryNote, DeliveryLine
        from inventory.services import post_delivery
        from core.models import DocumentStatus
        from inventory.models import StockBalance

        # Seed 10 rolls balance
        StockBalance.objects.create(
            item=self.item_su, location=self.loc,
            qty_on_hand=Decimal('10'), qty_reserved=Decimal('0'),
        )
        dn = DeliveryNote.objects.create(
            document_number='DN-SU-001',
            customer=self.customer, warehouse=self.wh,
            delivery_date=datetime.date.today(), created_by=self.user,
        )
        # Deliver 100 meters → 100/50 = 2 rolls deducted
        DeliveryLine.objects.create(
            delivery=dn, item=self.item_su, location=self.loc,
            qty=Decimal('100'), unit=self.meter,
        )
        post_delivery(dn, self.user)
        # 10 - 2 = 8 rolls
        self.assertEqual(_get_balance(self.item_su, self.loc), Decimal('8'))


class GRNthenDNDefaultUnitTest(TestCase):
    """GRN 4 rolls then DN 1 roll → net 3 rolls."""

    @classmethod
    def setUpTestData(cls):
        _setup(cls)

    def test_net_balance_in_rolls(self):
        from sales.models import DeliveryNote, DeliveryLine
        from inventory.services import post_delivery
        from core.models import DocumentStatus

        _post_grn(self, self.item_su, Decimal('4'), self.roll)   # +4 rolls
        dn = DeliveryNote.objects.create(
            document_number='DN-SU-002',
            customer=self.customer, warehouse=self.wh,
            delivery_date=datetime.date.today(), created_by=self.user,
        )
        DeliveryLine.objects.create(
            delivery=dn, item=self.item_su, location=self.loc,
            qty=Decimal('1'), unit=self.roll,
        )
        post_delivery(dn, self.user)   # -1 roll
        self.assertEqual(_get_balance(self.item_su, self.loc), Decimal('3'))


class TransferDefaultUnitTest(TestCase):
    """StockTransfer in meters normalises to rolls in both locations."""

    @classmethod
    def setUpTestData(cls):
        _setup(cls)

    def test_transfer_100_meters_moves_2_rolls(self):
        from inventory.models import StockTransfer, StockTransferLine, StockBalance
        from inventory.services import post_transfer
        from core.models import DocumentStatus

        StockBalance.objects.create(
            item=self.item_su, location=self.loc,
            qty_on_hand=Decimal('10'), qty_reserved=Decimal('0'),
        )
        tr = StockTransfer.objects.create(
            document_number='TR-SU-001',
            from_warehouse=self.wh, to_warehouse=self.wh,
            created_by=self.user,
        )
        # Transfer 100 meters → 100/50 = 2 rolls
        StockTransferLine.objects.create(
            transfer=tr, item=self.item_su,
            from_location=self.loc, to_location=self.loc2,
            qty=Decimal('100'), unit=self.meter,
        )
        post_transfer(tr, self.user)
        self.assertEqual(_get_balance(self.item_su, self.loc), Decimal('8'))
        self.assertEqual(_get_balance(self.item_su, self.loc2), Decimal('2'))


class DamagedReportDefaultUnitTest(TestCase):
    """Damaged report in meters → deducts rolls."""

    @classmethod
    def setUpTestData(cls):
        _setup(cls)

    def test_damaged_50_meters_deducts_1_roll(self):
        from inventory.models import DamagedReport, DamagedReportLine, StockBalance
        from inventory.services import post_damaged_report
        from core.models import DocumentStatus

        StockBalance.objects.create(
            item=self.item_su, location=self.loc,
            qty_on_hand=Decimal('10'), qty_reserved=Decimal('0'),
        )
        dr = DamagedReport.objects.create(
            document_number='DAM-SU-001', warehouse=self.wh,
            created_by=self.user,
        )
        # Damage 50 meters → 50/50 = 1 roll deducted
        DamagedReportLine.objects.create(
            report=dr, item=self.item_su, location=self.loc,
            qty=Decimal('50'), unit=self.meter,
        )
        post_damaged_report(dr, self.user)
        self.assertEqual(_get_balance(self.item_su, self.loc), Decimal('9'))


class ResyncDefaultUnitTest(TestCase):
    """Resync Phase 2 recalculates balance using default_unit."""

    @classmethod
    def setUpTestData(cls):
        _setup(cls)

    def test_resync_uses_default_unit(self):
        from inventory.models import StockBalance

        # GRN: 3 rolls → stored as 3 rolls (default_unit)
        _post_grn(self, self.item_su, Decimal('3'), self.roll)

        # Corrupt balance to simulate bad state
        StockBalance.objects.filter(item=self.item_su, location=self.loc).update(
            qty_on_hand=Decimal('999')
        )
        self.assertEqual(_get_balance(self.item_su, self.loc), Decimal('999'))

        _call_resync('--phase', '2')

        # Phase 2 replays GRN line: 3 rolls → 3 rolls (no conversion)
        self.assertEqual(_get_balance(self.item_su, self.loc), Decimal('3'))


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

        # item_su.stock_unit = roll (LENGTH); pcs is QUANTITY → invalid
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

        # item_su.stock_unit = roll (LENGTH); meter is also LENGTH → valid
        form = SalesOrderLineForm(data={
            'item': self.item_su.pk,
            'qty_ordered': '2',
            'unit': self.meter.pk,
            'unit_price': '10',
            'discount_type': 'PERCENT',
            'discount_value': '0',
        })
        self.assertTrue(form.is_valid(), form.errors)
