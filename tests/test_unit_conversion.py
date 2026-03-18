"""
Tests for:
  1. Unit.category field exists and defaults to 'quantity'
  2. UnitConversion.clean() blocks cross-category conversions
  3. convert_to_base_unit() accuracy (direct, reverse, identity)
  4. post_delivery converts qty to base-unit before deducting StockBalance
  5. post_goods_receipt converts qty to base-unit before adding StockBalance
  6. SalesOrderLineForm rejects cross-category unit
  7. seed_units management command creates all 50 standard units
  8. UnitViewSet ?category= filter works
"""
import datetime
from decimal import Decimal
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command
from io import StringIO

User = get_user_model()


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _make_item(code, name, cat, default_unit, cost_price=Decimal('100')):
    from catalog.models import Item, ItemType
    return Item.objects.create(
        code=code, name=name,
        item_type=ItemType.FINISHED,
        category=cat,
        default_unit=default_unit,
        cost_price=cost_price,
        selling_price=cost_price * 2,
    )


class UnitCategoryTestBase(TestCase):
    """Shared setUp: creates two categories and three units (pcs, box, kg)."""

    @classmethod
    def setUpTestData(cls):
        from catalog.models import Category, Unit, UnitCategory
        cls.cat_items = Category.objects.create(name='ItemCat', code='ICAT')
        cls.pcs = Unit.objects.create(
            name='TestPiece', abbreviation='tpcs', category=UnitCategory.QUANTITY)
        cls.box = Unit.objects.create(
            name='TestBox', abbreviation='tbx', category=UnitCategory.QUANTITY)
        cls.kg = Unit.objects.create(
            name='TestKg', abbreviation='tkg', category=UnitCategory.MASS)
        cls.user = User.objects.create_superuser('uc_u', 'uc@t.com', 'pass')


# ──────────────────────────────────────────────────────────────────────────────
# 1. Unit.category field
# ──────────────────────────────────────────────────────────────────────────────

class UnitCategoryFieldTest(UnitCategoryTestBase):

    def test_default_category_is_quantity(self):
        from catalog.models import Unit, UnitCategory
        u = Unit.objects.create(name='DefaultUnit', abbreviation='du1')
        self.assertEqual(u.category, UnitCategory.QUANTITY)

    def test_category_stored_correctly(self):
        from catalog.models import UnitCategory
        self.assertEqual(self.kg.category, UnitCategory.MASS)
        self.assertEqual(self.pcs.category, UnitCategory.QUANTITY)


# ──────────────────────────────────────────────────────────────────────────────
# 2. UnitConversion same-category validation
# ──────────────────────────────────────────────────────────────────────────────

class UnitConversionValidationTest(UnitCategoryTestBase):

    def test_same_category_conversion_valid(self):
        from catalog.models import UnitConversion
        conv = UnitConversion(from_unit=self.box, to_unit=self.pcs, factor=Decimal('20'))
        conv.clean()  # should NOT raise

    def test_cross_category_conversion_valid(self):
        from catalog.models import UnitConversion
        conv = UnitConversion(from_unit=self.box, to_unit=self.kg, factor=Decimal('5'))
        conv.clean()

    def test_self_conversion_raises(self):
        from catalog.models import UnitConversion
        conv = UnitConversion(from_unit=self.pcs, to_unit=self.pcs, factor=Decimal('1'))
        with self.assertRaises(ValidationError):
            conv.clean()


# ──────────────────────────────────────────────────────────────────────────────
# 3. convert_to_base_unit() accuracy
# ──────────────────────────────────────────────────────────────────────────────

class ConvertToBaseUnitTest(UnitCategoryTestBase):

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        from catalog.models import UnitConversion
        # 1 box = 20 pcs
        cls.conv_box_pcs = UnitConversion.objects.create(
            from_unit=cls.box, to_unit=cls.pcs, factor=Decimal('20'))

    def test_same_unit_returns_unchanged(self):
        from catalog.models import convert_to_base_unit
        result = convert_to_base_unit(Decimal('5'), self.pcs, self.pcs)
        self.assertEqual(result, Decimal('5'))

    def test_direct_conversion(self):
        from catalog.models import convert_to_base_unit
        result = convert_to_base_unit(Decimal('3'), self.box, self.pcs)
        self.assertEqual(result, Decimal('60'))  # 3 × 20

    def test_reverse_conversion(self):
        from catalog.models import convert_to_base_unit
        # 100 pcs → boxes using reverse of box→pcs (factor=20)  ⟹ 100/20 = 5
        result = convert_to_base_unit(Decimal('100'), self.pcs, self.box)
        self.assertEqual(result, Decimal('5'))

    def test_cross_category_conversion_works_when_configured(self):
        from catalog.models import UnitConversion, convert_to_base_unit
        UnitConversion.objects.create(
            from_unit=self.box,
            to_unit=self.kg,
            factor=Decimal('5'),
        )
        result = convert_to_base_unit(Decimal('3'), self.box, self.kg)
        self.assertEqual(result, Decimal('15'))

    def test_cross_category_raises_value_error_when_missing_conversion(self):
        from catalog.models import convert_to_base_unit
        with self.assertRaises(ValueError):
            convert_to_base_unit(Decimal('5'), self.kg, self.box)

    def test_missing_conversion_raises_value_error(self):
        from catalog.models import Unit, UnitCategory, convert_to_base_unit
        other = Unit.objects.create(
            name='TestYard', abbreviation='tyd', category=UnitCategory.QUANTITY)
        with self.assertRaises(ValueError):
            convert_to_base_unit(Decimal('5'), other, self.pcs)

    def test_fractional_reverse_conversion(self):
        from catalog.models import convert_to_base_unit
        # 10 pcs / 20 = 0.5 box
        result = convert_to_base_unit(Decimal('10'), self.pcs, self.box)
        self.assertEqual(result, Decimal('0.5'))


class ItemUnitConversionFormsetViewTest(UnitCategoryTestBase):

    def test_item_create_view_saves_multiple_item_specific_conversions(self):
        from django.urls import reverse
        from catalog.models import Item, UnitConversion, Unit, UnitCategory

        meter = Unit.objects.create(name='TestMeter', abbreviation='tm', category=UnitCategory.LENGTH)
        self.client.force_login(self.user)

        response = self.client.post(reverse('item_create'), {
            'code': 'ITM-CONV-001',
            'name': 'Convertible Product',
            'item_type': 'FINISHED',
            'category': self.cat_items.pk,
            'default_unit': self.pcs.pk,
            'selling_unit': self.pcs.pk,
            'description': '',
            'barcode': '',
            'cost_price': '100.00',
            'selling_price': '200.00',
            'minimum_stock': '1.00',
            'maximum_stock': '10.00',
            'reorder_point': '2.00',
            'conversions-TOTAL_FORMS': '2',
            'conversions-INITIAL_FORMS': '0',
            'conversions-MIN_NUM_FORMS': '0',
            'conversions-MAX_NUM_FORMS': '1000',
            'conversions-0-from_unit': self.box.pk,
            'conversions-0-to_unit': self.pcs.pk,
            'conversions-0-factor': '20',
            'conversions-1-from_unit': meter.pk,
            'conversions-1-to_unit': self.kg.pk,
            'conversions-1-factor': '3.5',
        })

        self.assertEqual(response.status_code, 302)
        item = Item.objects.get(code='ITM-CONV-001')
        conversions = UnitConversion.objects.filter(item=item).order_by('from_unit__name', 'to_unit__name')
        self.assertEqual(conversions.count(), 2)
        self.assertTrue(conversions.filter(from_unit=self.box, to_unit=self.pcs, factor=Decimal('20')).exists())
        self.assertTrue(conversions.filter(from_unit=meter, to_unit=self.kg, factor=Decimal('3.5')).exists())


# ──────────────────────────────────────────────────────────────────────────────
# 4. post_delivery converts to base unit for StockBalance
# ──────────────────────────────────────────────────────────────────────────────

class PostDeliveryUnitConversionTest(UnitCategoryTestBase):

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        from catalog.models import UnitConversion
        from warehouses.models import Warehouse, Location
        from partners.models import Customer
        from core.models import DocumentStatus

        # 1 box = 20 pcs
        cls.conv = UnitConversion.objects.create(
            from_unit=cls.box, to_unit=cls.pcs, factor=Decimal('20'))

        cls.wh = Warehouse.objects.create(name='WH_UC', code='WH_UC')
        cls.loc = Location.objects.create(
            name='Main_UC', code='MAIN_UC', warehouse=cls.wh)
        cls.customer = cls.customer if hasattr(cls, 'customer') else \
            Customer.objects.create(name='CustUC', code='CUC')

        cls.item = _make_item('ITM_UC_A', 'ItemUCA', cls.cat_items, cls.pcs)

    def _seed_stock(self, qty):
        from inventory.models import StockBalance
        StockBalance.objects.update_or_create(
            item=self.item, location=self.loc,
            defaults={'qty_on_hand': qty, 'qty_reserved': Decimal('0')},
        )

    def test_delivery_box_deducts_correct_pcs(self):
        """Deliver 3 boxes (×20 = 60 pcs) from 100 pcs stock → 40 pcs remaining."""
        from sales.models import DeliveryNote, DeliveryLine
        from inventory.services import post_delivery
        from inventory.models import StockBalance
        from core.models import DocumentStatus

        self._seed_stock(Decimal('100'))

        dn = DeliveryNote.objects.create(
            document_number='DN-UC-001',
            customer=self.customer,
            warehouse=self.wh,
            delivery_date=datetime.date.today(),
            created_by=self.user,
        )
        DeliveryLine.objects.create(
            delivery=dn, item=self.item,
            location=self.loc, qty=Decimal('3'), unit=self.box,
        )

        post_delivery(dn, self.user)

        bal = StockBalance.objects.get(item=self.item, location=self.loc)
        self.assertEqual(bal.qty_on_hand, Decimal('40'))  # 100 − 60

    def test_delivery_same_unit_deducts_exact(self):
        """Deliver 10 pcs from 100 pcs → 90 pcs."""
        from sales.models import DeliveryNote, DeliveryLine
        from inventory.services import post_delivery
        from inventory.models import StockBalance

        self._seed_stock(Decimal('100'))

        dn = DeliveryNote.objects.create(
            document_number='DN-UC-002',
            customer=self.customer,
            warehouse=self.wh,
            delivery_date=datetime.date.today(),
            created_by=self.user,
        )
        DeliveryLine.objects.create(
            delivery=dn, item=self.item,
            location=self.loc, qty=Decimal('10'), unit=self.pcs,
        )

        post_delivery(dn, self.user)

        bal = StockBalance.objects.get(item=self.item, location=self.loc)
        self.assertEqual(bal.qty_on_hand, Decimal('90'))


# ──────────────────────────────────────────────────────────────────────────────
# 5. post_goods_receipt converts to base unit for StockBalance
# ──────────────────────────────────────────────────────────────────────────────

class PostGRNUnitConversionTest(UnitCategoryTestBase):

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        from catalog.models import UnitConversion
        from warehouses.models import Warehouse, Location
        from partners.models import Supplier
        from procurement.models import PurchaseOrder

        # 1 box = 12 pcs
        cls.conv = UnitConversion.objects.create(
            from_unit=cls.box, to_unit=cls.pcs, factor=Decimal('12'))

        cls.wh = Warehouse.objects.create(name='WH_GRN_UC', code='WHGUC')
        cls.loc = Location.objects.create(
            name='Main_GRN', code='MGRN', warehouse=cls.wh)
        cls.supplier = Supplier.objects.create(name='SupUC', code='SUC')
        cls.item = _make_item('ITM_GRN_UC', 'ItemGRN', cls.cat_items, cls.pcs)

    def test_grn_box_adds_correct_pcs(self):
        """Receive 5 boxes (×12 = 60 pcs) into zero stock → 60 pcs."""
        from procurement.models import PurchaseOrder, GoodsReceipt, GoodsReceiptLine, PurchaseOrderLine
        from inventory.services import post_goods_receipt
        from inventory.models import StockBalance
        from core.models import DocumentStatus

        po = PurchaseOrder.objects.create(
            document_number='PO-UC-001',
            supplier=self.supplier,
            warehouse=self.wh,
            order_date=datetime.date.today(),
            created_by=self.user,
            status=DocumentStatus.APPROVED,
        )
        PurchaseOrderLine.objects.create(
            purchase_order=po, item=self.item,
            qty_ordered=Decimal('5'), unit=self.box, unit_price=Decimal('100'),
        )

        grn = GoodsReceipt.objects.create(
            document_number='GRN-UC-001',
            purchase_order=po,
            supplier=self.supplier,
            warehouse=self.wh,
            receipt_date=datetime.date.today(),
            created_by=self.user,
        )
        GoodsReceiptLine.objects.create(
            goods_receipt=grn, item=self.item,
            location=self.loc, qty=Decimal('5'), unit=self.box,
        )

        post_goods_receipt(grn, self.user)

        bal = StockBalance.objects.get(item=self.item, location=self.loc)
        self.assertEqual(bal.qty_on_hand, Decimal('60'))  # 5 × 12


# ──────────────────────────────────────────────────────────────────────────────
# 6. SalesOrderLineForm rejects cross-category unit
# ──────────────────────────────────────────────────────────────────────────────

class SalesOrderLineFormCategoryValidationTest(UnitCategoryTestBase):

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.item = _make_item('ITM_SLF', 'ItemSLF', cls.cat_items, cls.pcs)
        from warehouses.models import Warehouse
        from partners.models import Customer
        cls.wh = Warehouse.objects.create(name='WH_SLF', code='WHSLF')
        cls.customer = Customer.objects.create(name='CustSLF', code='CSLF')

    def _make_so(self):
        from sales.models import SalesOrder
        from core.models import DocumentStatus
        return SalesOrder.objects.create(
            document_number='SO-SLF-001',
            warehouse=self.wh,
            customer=self.customer,
            order_date=datetime.date.today(),
            created_by=self.user,
        )

    def test_valid_same_category_unit_passes(self):
        from sales.forms import SalesOrderLineForm
        so = self._make_so()
        form = SalesOrderLineForm(data={
            'item': self.item.pk,
            'qty_ordered': '5',
            'unit': self.pcs.pk,
            'unit_price': '200',
            'discount_type': 'PERCENT',
            'discount_value': '0',
        })
        form.is_valid()
        self.assertNotIn('unit', form.errors)

    def test_cross_category_unit_fails(self):
        from sales.forms import SalesOrderLineForm
        so = self._make_so()
        form = SalesOrderLineForm(data={
            'item': self.item.pk,
            'qty_ordered': '5',
            'unit': self.kg.pk,  # mass unit for a quantity-based item
            'unit_price': '200',
            'discount_type': 'PERCENT',
            'discount_value': '0',
        })
        form.is_valid()
        self.assertIn('unit', form.errors)


# ──────────────────────────────────────────────────────────────────────────────
# 7. seed_units management command
# ──────────────────────────────────────────────────────────────────────────────

class SeedUnitsCommandTest(TestCase):

    def test_seed_creates_all_standard_units(self):
        out = StringIO()
        call_command('seed_units', stdout=out)
        from catalog.models import Unit
        # All 50 units should now exist
        from catalog.management.commands.seed_units import UNITS
        for name, abbr, cat in UNITS:
            self.assertTrue(
                Unit.objects.filter(abbreviation=abbr).exists(),
                f'Unit with abbreviation "{abbr}" was not created.',
            )

    def test_seed_idempotent(self):
        """Running seed_units twice should not error or create duplicates."""
        out = StringIO()
        call_command('seed_units', stdout=out)
        call_command('seed_units', stdout=out)
        from catalog.models import Unit
        from catalog.management.commands.seed_units import UNITS
        for _, abbr, _ in UNITS:
            count = Unit.objects.filter(abbreviation=abbr).count()
            self.assertEqual(count, 1, f'Duplicate unit for abbreviation "{abbr}".')

    def test_seed_sets_correct_categories(self):
        out = StringIO()
        call_command('seed_units', stdout=out)
        from catalog.models import Unit, UnitCategory
        from catalog.management.commands.seed_units import UNITS
        for name, abbr, cat in UNITS:
            unit = Unit.objects.get(abbreviation=abbr)
            self.assertEqual(unit.category, cat,
                f'Unit {abbr}: expected category {cat}, got {unit.category}.')

    def test_update_existing_flag(self):
        """--update-existing should fix wrong categories."""
        from catalog.models import Unit, UnitCategory
        # Pre-create box with wrong category
        Unit.objects.update_or_create(
            abbreviation='bx',
            defaults={'name': 'Box', 'category': UnitCategory.MASS},
        )
        out = StringIO()
        call_command('seed_units', update_existing=True, stdout=out)
        box = Unit.objects.get(abbreviation='bx')
        self.assertEqual(box.category, UnitCategory.QUANTITY)


# ──────────────────────────────────────────────────────────────────────────────
# 8. UnitViewSet ?category= filter
# ──────────────────────────────────────────────────────────────────────────────

class UnitViewSetCategoryFilterTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        from catalog.models import Unit, UnitCategory
        cls.user = User.objects.create_superuser('uvsf_u', 'uv@t.com', 'pass')
        Unit.objects.create(name='ApiPiece', abbreviation='apcs', category=UnitCategory.QUANTITY)
        Unit.objects.create(name='ApiKg',    abbreviation='akg',  category=UnitCategory.MASS)
        Unit.objects.create(name='ApiMeter', abbreviation='am',   category=UnitCategory.LENGTH)

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.user)

    def test_filter_by_category_quantity(self):
        resp = self.client.get('/api/units/?category=quantity&page_size=200')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        results = data.get('results', data)
        cats = {u['category'] for u in results}
        self.assertIn('quantity', cats)
        self.assertNotIn('mass', cats)
        self.assertNotIn('length', cats)

    def test_filter_by_category_mass(self):
        resp = self.client.get('/api/units/?category=mass&page_size=200')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        results = data.get('results', data)
        cats = {u['category'] for u in results}
        self.assertIn('mass', cats)
        self.assertNotIn('quantity', cats)

    def test_unit_serializer_includes_category(self):
        resp = self.client.get('/api/units/?page_size=200')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        results = data.get('results', data)
        self.assertTrue(len(results) > 0)
        self.assertIn('category', results[0])
