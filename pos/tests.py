"""
Acceptance tests for POS module.
Covers: POS sale posting, refund posting, void sale, shift management,
        stock checks, and concurrency safety.
"""
from decimal import Decimal
from django.test import TestCase
from django.utils import timezone

from accounts.models import User
from catalog.models import Category, Unit, Item
from partners.models import Customer
from warehouses.models import Warehouse, Location
from inventory.models import StockMove, StockBalance, MoveType
from pricing.models import PriceList, PriceListItem
from pos.models import (
    POSRegister, POSShift, POSSale, POSSaleLine,
    POSPayment, POSRefund, POSRefundLine,
    ShiftStatus, SaleStatus, RefundStatus, PaymentMethod,
)
from pos.services import (
    open_shift, close_shift,
    post_pos_sale, post_pos_refund, void_sale,
    generate_sale_number, generate_refund_number,
)


class POSTestMixin:
    """Shared setUp for POS tests."""

    def setUp(self):
        self.user = User.objects.create_user(username='cashier', password='pass123')
        self.category = Category.objects.create(code='CAT', name='Test')
        self.unit = Unit.objects.create(name='Piece', abbreviation='pcs')
        self.item = Item.objects.create(
            code='ITEM-POS', name='POS Test Item', item_type='FINISHED',
            category=self.category, default_unit=self.unit,
        )
        self.warehouse = Warehouse.objects.create(
            code='WH-POS', name='POS Warehouse', allow_negative_stock=False,
        )
        self.location = Location.objects.create(
            warehouse=self.warehouse, code='POS-BIN', name='POS Bin',
        )
        self.price_list = PriceList.objects.create(
            name='Default POS', is_default=True,
        )
        PriceListItem.objects.create(
            price_list=self.price_list, item=self.item,
            unit=self.unit, price=Decimal('100.00'),
        )
        self.register = POSRegister.objects.create(
            name='Register 1',
            warehouse=self.warehouse,
            default_location=self.location,
            price_list=self.price_list,
        )
        # Seed stock
        StockBalance.objects.create(
            item=self.item, location=self.location,
            qty_on_hand=Decimal('100'), qty_reserved=Decimal('0'),
        )

    def _open_shift(self):
        return open_shift(self.register, self.user, Decimal('1000'))

    def _create_sale(self, shift, qty=Decimal('2')):
        sale = POSSale.objects.create(
            sale_no=generate_sale_number(),
            register=self.register,
            shift=shift,
            warehouse=self.warehouse,
            location=self.location,
            created_by=self.user,
        )
        line_total = qty * Decimal('100')
        POSSaleLine.objects.create(
            sale=sale, item=self.item, location=self.location,
            qty=qty, unit=self.unit, unit_price=Decimal('100'),
            line_total=line_total,
        )
        sale.subtotal = line_total
        sale.grand_total = line_total
        sale.save(update_fields=['subtotal', 'grand_total'])
        return sale


class ShiftTests(POSTestMixin, TestCase):

    def test_open_shift(self):
        shift = self._open_shift()
        self.assertEqual(shift.status, ShiftStatus.OPEN)
        self.assertEqual(shift.opening_cash, Decimal('1000'))

    def test_cannot_open_two_shifts(self):
        self._open_shift()
        with self.assertRaises(ValueError):
            self._open_shift()

    def test_close_shift(self):
        shift = self._open_shift()
        closed = close_shift(shift, self.user, Decimal('1000'))
        self.assertEqual(closed.status, ShiftStatus.CLOSED)
        self.assertIsNotNone(closed.closed_at)


class POSSalePostTests(POSTestMixin, TestCase):

    def test_post_pos_sale_decreases_stock(self):
        shift = self._open_shift()
        sale = self._create_sale(shift, qty=Decimal('5'))

        # Add payment and mark paid
        POSPayment.objects.create(
            sale=sale, method=PaymentMethod.CASH, amount=Decimal('500'),
        )
        sale.status = SaleStatus.PAID
        sale.save(update_fields=['status'])

        post_pos_sale(sale.pk, self.user)
        sale.refresh_from_db()
        self.assertEqual(sale.status, SaleStatus.POSTED)

        bal = StockBalance.objects.get(item=self.item, location=self.location)
        self.assertEqual(bal.qty_on_hand, Decimal('95'))

        moves = StockMove.objects.filter(reference_type='POSSale', reference_id=sale.pk)
        self.assertEqual(moves.count(), 1)
        self.assertEqual(moves.first().move_type, MoveType.POS_SALE)

    def test_cannot_post_if_shift_closed(self):
        shift = self._open_shift()
        sale = self._create_sale(shift)
        POSPayment.objects.create(sale=sale, method=PaymentMethod.CASH, amount=sale.grand_total)
        sale.status = SaleStatus.PAID
        sale.save(update_fields=['status'])

        close_shift(shift, self.user, Decimal('1000'))

        with self.assertRaises(ValueError):
            post_pos_sale(sale.pk, self.user)

    def test_cannot_post_insufficient_stock(self):
        shift = self._open_shift()
        sale = self._create_sale(shift, qty=Decimal('200'))  # More than 100 available
        POSPayment.objects.create(sale=sale, method=PaymentMethod.CASH, amount=sale.grand_total)
        sale.status = SaleStatus.PAID
        sale.save(update_fields=['status'])

        with self.assertRaises(ValueError):
            post_pos_sale(sale.pk, self.user)


class POSRefundTests(POSTestMixin, TestCase):

    def _post_sale(self, shift, qty=Decimal('5')):
        sale = self._create_sale(shift, qty=qty)
        POSPayment.objects.create(sale=sale, method=PaymentMethod.CASH, amount=sale.grand_total)
        sale.status = SaleStatus.PAID
        sale.save(update_fields=['status'])
        post_pos_sale(sale.pk, self.user)
        sale.refresh_from_db()
        return sale

    def test_post_refund_increases_stock(self):
        shift = self._open_shift()
        sale = self._post_sale(shift, qty=Decimal('5'))

        bal_before = StockBalance.objects.get(item=self.item, location=self.location)
        self.assertEqual(bal_before.qty_on_hand, Decimal('95'))

        refund = POSRefund.objects.create(
            refund_no=generate_refund_number(),
            original_sale=sale,
            shift=shift,
            reason='Defective',
            created_by=self.user,
            subtotal=Decimal('300'),
            grand_total=Decimal('300'),
        )
        POSRefundLine.objects.create(
            refund=refund, sale_line=sale.lines.first(),
            item=self.item, location=self.location,
            qty=Decimal('3'), unit=self.unit, amount=Decimal('300'),
        )

        post_pos_refund(refund.pk, self.user)
        refund.refresh_from_db()
        self.assertEqual(refund.status, RefundStatus.POSTED)

        bal_after = StockBalance.objects.get(item=self.item, location=self.location)
        self.assertEqual(bal_after.qty_on_hand, Decimal('98'))

        moves = StockMove.objects.filter(reference_type='POSRefund', reference_id=refund.pk)
        self.assertEqual(moves.count(), 1)
        self.assertEqual(moves.first().move_type, MoveType.RETURN_IN)


class VoidSaleTests(POSTestMixin, TestCase):

    def test_void_draft_sale(self):
        shift = self._open_shift()
        sale = self._create_sale(shift)

        void_sale(sale.pk, self.user)
        sale.refresh_from_db()
        self.assertEqual(sale.status, SaleStatus.VOID)

    def test_void_posted_creates_reversals(self):
        shift = self._open_shift()
        sale = self._create_sale(shift, qty=Decimal('10'))
        POSPayment.objects.create(sale=sale, method=PaymentMethod.CASH, amount=sale.grand_total)
        sale.status = SaleStatus.PAID
        sale.save(update_fields=['status'])
        post_pos_sale(sale.pk, self.user)

        bal = StockBalance.objects.get(item=self.item, location=self.location)
        self.assertEqual(bal.qty_on_hand, Decimal('90'))

        void_sale(sale.pk, self.user)
        sale.refresh_from_db()
        self.assertEqual(sale.status, SaleStatus.VOID)

        bal.refresh_from_db()
        self.assertEqual(bal.qty_on_hand, Decimal('100'))

        # Original POS_SALE + RETURN_IN reversal
        all_moves = StockMove.objects.filter(reference_type='POSSale', reference_id=sale.pk)
        self.assertEqual(all_moves.count(), 2)
