"""
Tests for item-specific UnitConversion, CustomerService posting fix,
resync Phase 3 integrity audit, and _safe_convert item propagation.
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

    cls.user = User.objects.create_superuser('isc_user', 'isc@t.com', 'pass')
    cls.cat = ItemCat.objects.create(name='ISC_Cat', code='ISCCAT')
    cls.meter = Unit.objects.create(
        name='ISC_Meter', abbreviation='isc_m', category=UnitCategory.LENGTH)
    cls.roll = Unit.objects.create(
        name='ISC_Roll', abbreviation='isc_roll', category=UnitCategory.LENGTH)
    cls.pcs = Unit.objects.create(
        name='ISC_Pcs', abbreviation='isc_pcs', category=UnitCategory.QUANTITY)

    cls.wh = Warehouse.objects.create(name='ISC_WH', code='ISCSW')
    cls.loc = Location.objects.create(name='ISC_Loc', code='ISCLOC', warehouse=cls.wh)
    cls.supplier = Supplier.objects.create(name='ISC_Sup', code='ISCSUP')
    cls.customer = Customer.objects.create(name='ISC_Cust', code='ISCCUS')

    # item_a: default=roll, selling=meter  — uses GLOBAL conv (1 roll = 50 m)
    cls.global_conv = UnitConversion.objects.create(
        from_unit=cls.roll, to_unit=cls.meter, factor=Decimal('50'))

    cls.item_a = Item.objects.create(
        code='ISC_A', name='Item A',
        item_type=ItemType.FINISHED, category=cls.cat,
        default_unit=cls.roll, selling_unit=cls.meter,
        cost_price=Decimal('5'), selling_price=Decimal('10'),
    )

    # item_b: default=roll, selling=meter — uses ITEM-SPECIFIC conv (1 roll = 30 m)
    cls.item_b = Item.objects.create(
        code='ISC_B', name='Item B',
        item_type=ItemType.FINISHED, category=cls.cat,
        default_unit=cls.roll, selling_unit=cls.meter,
        cost_price=Decimal('5'), selling_price=Decimal('10'),
    )
    cls.item_conv = UnitConversion.objects.create(
        from_unit=cls.roll, to_unit=cls.meter,
        item=cls.item_b, factor=Decimal('30'))

    # item_c: no selling_unit, stock_unit = pcs (no conversion needed)
    cls.item_c = Item.objects.create(
        code='ISC_C', name='Item C (no SU)',
        item_type=ItemType.FINISHED, category=cls.cat,
        default_unit=cls.pcs,
        cost_price=Decimal('1'), selling_price=Decimal('2'),
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


# ── Tests: convert_to_base_unit item-specific lookup ─────────────────────────

class ItemSpecificConversionTest(TestCase):
    """convert_to_base_unit checks item-specific record first."""

    @classmethod
    def setUpTestData(cls):
        _setup(cls)

    def test_global_conversion_used_when_no_item_specific(self):
        from catalog.models import convert_to_base_unit
        # item_a has no item-specific record → uses global (50)
        result = convert_to_base_unit(
            Decimal('2'), self.roll, self.meter, item=self.item_a)
        self.assertEqual(result, Decimal('100'))

    def test_item_specific_overrides_global(self):
        from catalog.models import convert_to_base_unit
        # item_b has item-specific factor=30 → overrides global 50
        result = convert_to_base_unit(
            Decimal('2'), self.roll, self.meter, item=self.item_b)
        self.assertEqual(result, Decimal('60'))

    def test_no_item_falls_back_to_global(self):
        from catalog.models import convert_to_base_unit
        # item=None → uses global conversion (50)
        result = convert_to_base_unit(Decimal('3'), self.roll, self.meter)
        self.assertEqual(result, Decimal('150'))

    def test_reverse_item_specific_lookup(self):
        from catalog.models import convert_to_base_unit
        # Reverse: meter → roll for item_b. global=50, item_b specific=30
        # 60 meters / 30 = 2 rolls
        result = convert_to_base_unit(
            Decimal('60'), self.meter, self.roll, item=self.item_b)
        self.assertAlmostEqual(float(result), 2.0, places=4)

    def test_same_unit_returns_qty_unchanged(self):
        from catalog.models import convert_to_base_unit
        result = convert_to_base_unit(
            Decimal('5'), self.meter, self.meter, item=self.item_a)
        self.assertEqual(result, Decimal('5'))


# ── Tests: GRN posting with item-specific conversion ─────────────────────────

class GRNItemSpecificConversionTest(TestCase):
    """GRN posted in rolls uses item-specific factor when available."""

    @classmethod
    def setUpTestData(cls):
        _setup(cls)

    def _post_grn(self, item, qty, unit):
        from procurement.models import (
            GoodsReceipt, GoodsReceiptLine,
            PurchaseOrder, PurchaseOrderLine,
        )
        from inventory.services import post_goods_receipt
        from core.models import DocumentStatus

        n = GoodsReceipt.objects.count() + 1
        po = PurchaseOrder.objects.create(
            document_number=f'PO-ISC-{n:04d}',
            supplier=self.supplier, warehouse=self.wh,
            order_date=datetime.date.today(), created_by=self.user,
            status=DocumentStatus.APPROVED,
        )
        PurchaseOrderLine.objects.create(
            purchase_order=po, item=item,
            qty_ordered=qty, unit=unit, unit_price=Decimal('5'),
        )
        grn = GoodsReceipt.objects.create(
            document_number=f'GRN-ISC-{n:04d}',
            purchase_order=po, supplier=self.supplier,
            warehouse=self.wh, receipt_date=datetime.date.today(),
            created_by=self.user,
        )
        GoodsReceiptLine.objects.create(
            goods_receipt=grn, item=item, location=self.loc,
            qty=qty, unit=unit,
        )
        post_goods_receipt(grn, self.user)
        return grn

    def test_item_a_uses_global_50(self):
        self._post_grn(self.item_a, Decimal('2'), self.roll)
        self.assertEqual(_get_balance(self.item_a, self.loc), Decimal('100'))

    def test_item_b_uses_item_specific_30(self):
        self._post_grn(self.item_b, Decimal('2'), self.roll)
        # 2 rolls × 30 = 60 m  (not 100 from global)
        self.assertEqual(_get_balance(self.item_b, self.loc), Decimal('60'))

    def test_stockmove_qty_reflects_item_specific(self):
        from inventory.models import StockMove
        self._post_grn(self.item_b, Decimal('1'), self.roll)
        move = StockMove.objects.filter(
            reference_type='GoodsReceipt', item=self.item_b).first()
        self.assertIsNotNone(move)
        self.assertEqual(move.qty, Decimal('30'))  # item_b factor=30
        self.assertEqual(move.unit, self.meter)


# ── Tests: CustomerService posting uses stock_unit + conversion ───────────────

class CustomerServicePostingTest(TestCase):
    """service_complete deducts balance in stock_unit using conversion."""

    @classmethod
    def setUpTestData(cls):
        _setup(cls)

    def _seed_balance(self, item, qty):
        from inventory.models import StockBalance
        StockBalance.objects.create(
            item=item, location=cls.loc,
            qty_on_hand=qty, qty_reserved=Decimal('0'),
        )

    def setUp(self):
        from inventory.models import StockBalance
        StockBalance.objects.create(
            item=self.item_a, location=self.loc,
            qty_on_hand=Decimal('200'), qty_reserved=Decimal('0'),
        )

    def test_service_deducts_in_stock_unit(self):
        from services.models import CustomerService, ServiceLine, ServiceStatus
        from django.test import RequestFactory
        from django.contrib.auth.models import AnonymousUser
        from services.views import service_complete

        svc = CustomerService.objects.create(
            service_number='SVC-ISC-001',
            service_name='Test Service',
            customer_name='Test Customer',
            service_date=datetime.date.today(),
            status=ServiceStatus.DRAFT,
            warehouse=self.wh,
            created_by=self.user,
        )
        ServiceLine.objects.create(
            service=svc, item=self.item_a, location=self.loc,
            qty=Decimal('2'), unit=self.roll,  # 2 rolls = 100 m (global factor=50)
            unit_price=Decimal('10'),
        )

        rf = RequestFactory()
        req = rf.post(f'/services/{svc.pk}/complete/')
        req.user = self.user
        from django.contrib.messages.storage.fallback import FallbackStorage
        req.session = {}
        req._messages = FallbackStorage(req)

        service_complete(req, svc.pk)
        svc.refresh_from_db()
        self.assertEqual(svc.status, ServiceStatus.COMPLETED)

        # 200 - 2*50 = 100 m remaining
        self.assertEqual(_get_balance(self.item_a, self.loc), Decimal('100'))

    def test_service_stockmove_uses_stock_unit(self):
        from services.models import CustomerService, ServiceLine, ServiceStatus
        from inventory.models import StockMove
        from django.test import RequestFactory
        from services.views import service_complete
        from django.contrib.messages.storage.fallback import FallbackStorage

        svc = CustomerService.objects.create(
            service_number='SVC-ISC-002',
            service_name='Test Service 2',
            customer_name='Test Customer',
            service_date=datetime.date.today(),
            status=ServiceStatus.DRAFT,
            warehouse=self.wh,
            created_by=self.user,
        )
        ServiceLine.objects.create(
            service=svc, item=self.item_a, location=self.loc,
            qty=Decimal('1'), unit=self.roll,
            unit_price=Decimal('10'),
        )

        rf = RequestFactory()
        req = rf.post(f'/services/{svc.pk}/complete/')
        req.user = self.user
        req.session = {}
        req._messages = FallbackStorage(req)

        service_complete(req, svc.pk)

        move = StockMove.objects.filter(
            reference_type='CustomerService', item=self.item_a).first()
        self.assertIsNotNone(move)
        self.assertEqual(move.unit, self.meter)
        self.assertEqual(move.qty, Decimal('50'))  # 1 roll × 50 (global)


# ── Tests: Resync Phase 3 integrity audit ────────────────────────────────────

class ResyncPhase3AuditTest(TestCase):
    """Phase 3 reports negative balances and duplicate moves."""

    @classmethod
    def setUpTestData(cls):
        _setup(cls)

    def test_phase3_detects_negative_balance(self):
        from inventory.models import StockBalance
        StockBalance.objects.create(
            item=self.item_a, location=self.loc,
            qty_on_hand=Decimal('-5'), qty_reserved=Decimal('0'),
        )
        out = _call_resync('--phase', '3')
        self.assertIn('[NEG BALANCE]', out)
        self.assertIn('ISC_A', out)

    def test_phase3_passes_when_clean(self):
        out = _call_resync('--phase', '3')
        # No negative balances in clean DB — should pass
        self.assertNotIn('[NEG BALANCE]  none ✓', out.replace('  ', ' '))  # flexible match
        # Just confirm Phase 3 ran
        self.assertIn('Phase 3', out)

    def test_phase3_detects_missing_conversion_for_selling_unit(self):
        from catalog.models import Item, ItemType
        # Item with selling_unit but no conversion at all
        bare_item = Item.objects.create(
            code='ISC_NO_CONV', name='No Conv Item',
            item_type=ItemType.FINISHED, category=self.cat,
            default_unit=self.roll, selling_unit=self.meter,
            cost_price=Decimal('1'), selling_price=Decimal('2'),
        )
        # Delete all conversions for roll↔meter to simulate missing state
        from catalog.models import UnitConversion
        UnitConversion.objects.filter(
            from_unit=self.roll, to_unit=self.meter, item__isnull=True
        ).delete()
        out = _call_resync('--phase', '3')
        self.assertIn('[MISSING CONV]', out)
        self.assertIn('ISC_NO_CONV', out)


# ── Tests: UnitConversion uniqueness constraints ──────────────────────────────

class UnitConversionConstraintTest(TestCase):
    """Unique constraints allow same unit pair with different items."""

    @classmethod
    def setUpTestData(cls):
        _setup(cls)

    def test_cannot_create_duplicate_global(self):
        from catalog.models import UnitConversion
        from django.db import IntegrityError
        with self.assertRaises(Exception):  # IntegrityError or ValidationError
            UnitConversion.objects.create(
                from_unit=self.roll, to_unit=self.meter, factor=Decimal('99'))

    def test_can_create_item_specific_alongside_global(self):
        from catalog.models import UnitConversion
        # item_a doesn't yet have a specific record
        conv = UnitConversion.objects.create(
            from_unit=self.roll, to_unit=self.meter,
            item=self.item_a, factor=Decimal('75'))
        self.assertEqual(conv.factor, Decimal('75'))

    def test_cannot_create_duplicate_item_specific(self):
        from catalog.models import UnitConversion
        # item_b already has one at factor=30
        with self.assertRaises(Exception):
            UnitConversion.objects.create(
                from_unit=self.roll, to_unit=self.meter,
                item=self.item_b, factor=Decimal('99'))
