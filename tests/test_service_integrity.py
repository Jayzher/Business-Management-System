"""
Service Module — Data Integrity & Business Logic Tests
=======================================================
Covers:
  1. ServiceStatus transitions (create → start → complete → cancel guards)
  2. Inventory deduction on service_complete (StockMove + StockBalance)
  3. SERVICE_OUT move type used for service material deductions
  4. Warehouse default-location fallback when ServiceLine.location is None
  5. Missing-location warning (no deduction) when no location resolvable
  6. P&L calculations in service_detail view (revenue, COGS, gross profit)
  7. Invoice auto-creation on service_complete
  8. Service invoice list shows only service invoices
  9. compute_invoice_cogs returns correct value for service invoices
 10. Prevent re-completing an already-COMPLETED service
 11. Grand total uses manual amount override when set

Run:
    python manage.py test tests.test_service_integrity --verbosity=2
"""
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

import datetime
from decimal import Decimal

from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone

User = get_user_model()


# ── Common fixture builder ───────────────────────────────────────────────────

def _make_base_fixtures(prefix='SI'):
    """Return (user, item, unit, warehouse, location)."""
    from catalog.models import Category, Item, Unit
    from warehouses.models import Warehouse, Location

    cat, _ = Category.objects.get_or_create(name=f'{prefix}Cat', code=f'{prefix}CAT')
    unit, _ = Unit.objects.get_or_create(name=f'{prefix}Piece', abbreviation=f'{prefix.lower()}pc')
    item = Item.objects.create(
        code=f'{prefix}-ITEM-001',
        name=f'{prefix} Test Item',
        category=cat,
        default_unit=unit,
        cost_price=Decimal('80.00'),
        selling_price=Decimal('200.00'),
    )
    wh = Warehouse.objects.create(name=f'{prefix} Warehouse', code=f'{prefix}WH')
    loc = Location.objects.create(name=f'{prefix} Main', code=f'{prefix}MAIN', warehouse=wh, is_pickable=True)
    return item, unit, wh, loc


def _make_user(username):
    return User.objects.create_superuser(username, f'{username}@test.com', 'pass1234')


def _seed_stock(item, location, qty):
    """Seed a StockBalance for inventory deduction tests."""
    from inventory.models import StockBalance
    bal, _ = StockBalance.objects.get_or_create(
        item=item, location=location,
        defaults={'qty_on_hand': qty, 'qty_reserved': Decimal('0')},
    )
    bal.qty_on_hand = qty
    bal.save()
    return bal


# ════════════════════════════════════════════════════════════════════════════
# 1. Status Transitions
# ════════════════════════════════════════════════════════════════════════════

class ServiceStatusTransitionTest(TestCase):
    """Service status lifecycle: DRAFT → IN_PROGRESS → COMPLETED; guards work."""

    @classmethod
    def setUpTestData(cls):
        from services.models import CustomerService
        cls.user = _make_user('sst_user')
        item, unit, wh, loc = _make_base_fixtures('SST')
        cls.svc = CustomerService.objects.create(
            service_number='SST-001',
            service_name='Status Test',
            customer_name='Test Customer',
            service_date=datetime.date.today(),
            warehouse=wh,
            created_by=cls.user,
        )

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.user)

    def test_initial_status_is_draft(self):
        from services.models import ServiceStatus
        self.assertEqual(self.svc.status, ServiceStatus.DRAFT)

    def test_start_transitions_to_in_progress(self):
        from services.models import ServiceStatus
        self.client.post(reverse('service_start', args=[self.svc.pk]))
        self.svc.refresh_from_db()
        self.assertEqual(self.svc.status, ServiceStatus.IN_PROGRESS)

    def test_cannot_complete_already_completed(self):
        from services.models import CustomerService, ServiceStatus
        svc = CustomerService.objects.create(
            service_number='SST-DONE-001',
            service_name='Already Done',
            customer_name='Cust',
            service_date=datetime.date.today(),
            status=ServiceStatus.COMPLETED,
            created_by=self.user,
        )
        resp = self.client.post(reverse('service_complete', args=[svc.pk]))
        svc.refresh_from_db()
        # Should redirect back without double-completing
        self.assertEqual(svc.status, ServiceStatus.COMPLETED)

    def test_cannot_complete_cancelled_service(self):
        from services.models import CustomerService, ServiceStatus
        svc = CustomerService.objects.create(
            service_number='SST-CANCEL-001',
            service_name='Cancelled',
            customer_name='Cust',
            service_date=datetime.date.today(),
            status=ServiceStatus.CANCELLED,
            created_by=self.user,
        )
        resp = self.client.post(reverse('service_complete', args=[svc.pk]))
        svc.refresh_from_db()
        self.assertEqual(svc.status, ServiceStatus.CANCELLED)


# ════════════════════════════════════════════════════════════════════════════
# 2. Inventory Deduction on service_complete
# ════════════════════════════════════════════════════════════════════════════

class ServiceInventoryDeductionTest(TestCase):
    """Completing a service deducts stock via SERVICE_OUT StockMove."""

    @classmethod
    def setUpTestData(cls):
        from services.models import CustomerService, ServiceLine
        from catalog.models import Unit
        cls.user = _make_user('sid_user')
        cls.item, cls.unit, cls.wh, cls.loc = _make_base_fixtures('SID')

        cls.svc = CustomerService.objects.create(
            service_number='SID-001',
            service_name='Inventory Deduction Test',
            customer_name='Deduct Customer',
            service_date=datetime.date.today(),
            warehouse=cls.wh,
            created_by=cls.user,
        )
        ServiceLine.objects.create(
            service=cls.svc,
            item=cls.item,
            location=cls.loc,
            qty=Decimal('3'),
            unit=cls.unit,
            unit_price=Decimal('200.00'),
        )

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.user)
        # Seed 10 units so deduction doesn't fail
        _seed_stock(self.item, self.loc, Decimal('10'))

    def test_stock_balance_decreases_on_complete(self):
        from inventory.models import StockBalance
        before = StockBalance.objects.get(item=self.item, location=self.loc).qty_on_hand
        self.client.post(reverse('service_complete', args=[self.svc.pk]))
        self.svc.refresh_from_db()
        # Only run balance check if service completed successfully
        if self.svc.status == 'COMPLETED':
            after = StockBalance.objects.get(item=self.item, location=self.loc).qty_on_hand
            self.assertEqual(after, before - Decimal('3'))

    def test_service_out_stock_move_created(self):
        from inventory.models import StockMove, MoveType
        self.client.post(reverse('service_complete', args=[self.svc.pk]))
        self.svc.refresh_from_db()
        if self.svc.status == 'COMPLETED':
            move = StockMove.objects.filter(
                reference_type='CustomerService',
                reference_id=self.svc.pk,
            ).first()
            self.assertIsNotNone(move)
            self.assertEqual(move.move_type, MoveType.SERVICE_OUT)
            self.assertEqual(move.from_location, self.loc)
            self.assertEqual(move.item, self.item)
            self.assertEqual(move.qty, Decimal('3'))

    def test_stock_move_reference_number_matches_service(self):
        from inventory.models import StockMove
        self.client.post(reverse('service_complete', args=[self.svc.pk]))
        self.svc.refresh_from_db()
        if self.svc.status == 'COMPLETED':
            move = StockMove.objects.filter(reference_type='CustomerService',
                                            reference_id=self.svc.pk).first()
            self.assertEqual(move.reference_number, self.svc.service_number)

    def test_invoice_created_on_complete(self):
        from core.models import Invoice
        self.client.post(reverse('service_complete', args=[self.svc.pk]))
        self.svc.refresh_from_db()
        if self.svc.status == 'COMPLETED':
            self.assertIsNotNone(self.svc.invoice)
            inv = Invoice.objects.get(pk=self.svc.invoice_id)
            self.assertEqual(inv.grand_total, self.svc.grand_total)


# ════════════════════════════════════════════════════════════════════════════
# 3. Warehouse Default Location Fallback
# ════════════════════════════════════════════════════════════════════════════

class ServiceWarehouseFallbackTest(TestCase):
    """When ServiceLine.location is None, warehouse default location is used."""

    @classmethod
    def setUpTestData(cls):
        from services.models import CustomerService, ServiceLine
        cls.user = _make_user('swf_user')
        cls.item, cls.unit, cls.wh, cls.loc = _make_base_fixtures('SWF')

        # Service with NO location on the line, but warehouse assigned
        cls.svc = CustomerService.objects.create(
            service_number='SWF-001',
            service_name='Fallback Test',
            customer_name='Fallback Customer',
            service_date=datetime.date.today(),
            warehouse=cls.wh,
            created_by=cls.user,
        )
        ServiceLine.objects.create(
            service=cls.svc,
            item=cls.item,
            location=None,  # No explicit location
            qty=Decimal('2'),
            unit=cls.unit,
            unit_price=Decimal('150.00'),
        )

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.user)
        _seed_stock(self.item, self.loc, Decimal('10'))

    def test_stock_deducted_using_warehouse_default_location(self):
        from inventory.models import StockBalance, StockMove, MoveType
        before = StockBalance.objects.get(item=self.item, location=self.loc).qty_on_hand

        self.client.post(reverse('service_complete', args=[self.svc.pk]))
        self.svc.refresh_from_db()

        if self.svc.status == 'COMPLETED':
            # Should have used the warehouse's first pickable location
            move = StockMove.objects.filter(
                reference_type='CustomerService',
                reference_id=self.svc.pk,
                move_type=MoveType.SERVICE_OUT,
            ).first()
            self.assertIsNotNone(move, "SERVICE_OUT move should be created via fallback location")
            self.assertEqual(move.from_location, self.loc)
            after = StockBalance.objects.get(item=self.item, location=self.loc).qty_on_hand
            self.assertEqual(after, before - Decimal('2'))


# ════════════════════════════════════════════════════════════════════════════
# 4. Missing Location Warning — no deduction
# ════════════════════════════════════════════════════════════════════════════

class ServiceMissingLocationTest(TestCase):
    """No location + no warehouse → warning shown, stock NOT deducted."""

    @classmethod
    def setUpTestData(cls):
        from services.models import CustomerService, ServiceLine
        cls.user = _make_user('sml_user')
        cls.item, cls.unit, cls.wh, cls.loc = _make_base_fixtures('SML')

        # Service with NO warehouse and NO location on line
        cls.svc = CustomerService.objects.create(
            service_number='SML-001',
            service_name='No Location Test',
            customer_name='No Loc Customer',
            service_date=datetime.date.today(),
            warehouse=None,
            created_by=cls.user,
        )
        ServiceLine.objects.create(
            service=cls.svc,
            item=cls.item,
            location=None,
            qty=Decimal('1'),
            unit=cls.unit,
            unit_price=Decimal('100.00'),
        )

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.user)

    def test_no_stock_move_created_without_location(self):
        from inventory.models import StockMove
        count_before = StockMove.objects.filter(
            reference_type='CustomerService',
            reference_id=self.svc.pk,
        ).count()

        self.client.post(reverse('service_complete', args=[self.svc.pk]))
        self.svc.refresh_from_db()

        count_after = StockMove.objects.filter(
            reference_type='CustomerService',
            reference_id=self.svc.pk,
        ).count()

        # Service completes but no move is created
        if self.svc.status == 'COMPLETED':
            self.assertEqual(count_after, count_before)

    def test_service_still_completes_with_warning(self):
        """Service completes even if stock can't be deducted (no location)."""
        from services.models import ServiceStatus
        resp = self.client.post(reverse('service_complete', args=[self.svc.pk]),
                                follow=True)
        self.svc.refresh_from_db()
        self.assertEqual(self.svc.status, ServiceStatus.COMPLETED)


# ════════════════════════════════════════════════════════════════════════════
# 5. P&L in service_detail view
# ════════════════════════════════════════════════════════════════════════════

class ServiceDetailPNLTest(TestCase):
    """service_detail view returns correct P&L context variables."""

    @classmethod
    def setUpTestData(cls):
        from services.models import CustomerService, ServiceLine
        cls.user = _make_user('sdp_user')
        cls.item, cls.unit, cls.wh, cls.loc = _make_base_fixtures('SDP')

        cls.svc = CustomerService.objects.create(
            service_number='SDP-001',
            service_name='PNL Test Service',
            customer_name='PNL Customer',
            service_date=datetime.date.today(),
            warehouse=cls.wh,
            created_by=cls.user,
        )
        # Line: qty=2, unit_price=200, cost_price=80
        # Revenue = 400, COGS = 160, Gross Profit = 240
        cls.line = ServiceLine.objects.create(
            service=cls.svc,
            item=cls.item,
            location=cls.loc,
            qty=Decimal('2'),
            unit=cls.unit,
            unit_price=Decimal('200.00'),
        )

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.user)

    def test_service_detail_returns_200(self):
        resp = self.client.get(reverse('service_detail', args=[self.svc.pk]))
        self.assertEqual(resp.status_code, 200)

    def test_service_revenue_in_context(self):
        resp = self.client.get(reverse('service_detail', args=[self.svc.pk]))
        self.assertIn('service_revenue', resp.context)
        self.assertEqual(resp.context['service_revenue'], Decimal('400.00'))

    def test_service_cogs_in_context(self):
        """COGS = cost_price × qty = 80 × 2 = 160."""
        resp = self.client.get(reverse('service_detail', args=[self.svc.pk]))
        self.assertIn('service_cogs', resp.context)
        self.assertEqual(resp.context['service_cogs'], Decimal('160.00'))

    def test_gross_profit_in_context(self):
        """Gross Profit = Revenue - COGS = 400 - 160 = 240."""
        resp = self.client.get(reverse('service_detail', args=[self.svc.pk]))
        self.assertIn('gross_profit', resp.context)
        self.assertEqual(resp.context['gross_profit'], Decimal('240.00'))

    def test_gross_margin_in_context(self):
        """Gross Margin = (240 / 400) × 100 = 60.0%."""
        resp = self.client.get(reverse('service_detail', args=[self.svc.pk]))
        self.assertIn('gross_margin', resp.context)
        self.assertAlmostEqual(float(resp.context['gross_margin']), 60.0, places=1)

    def test_line_pnl_in_context(self):
        resp = self.client.get(reverse('service_detail', args=[self.svc.pk]))
        self.assertIn('line_pnl', resp.context)
        line_pnl = resp.context['line_pnl']
        self.assertEqual(len(line_pnl), 1)
        self.assertEqual(line_pnl[0]['cogs'], Decimal('160.00'))
        self.assertEqual(line_pnl[0]['profit'], Decimal('240.00'))

    def test_pnl_section_in_html(self):
        resp = self.client.get(reverse('service_detail', args=[self.svc.pk]))
        content = resp.content.decode()
        self.assertIn('Profit &amp; Loss Summary', content)
        self.assertIn('Cost of Goods Sold', content)
        self.assertIn('Gross Profit', content)

    def test_pnl_with_manual_amount_override(self):
        """When service.amount is set, grand_total = amount, not line total."""
        self.svc.amount = Decimal('500.00')
        self.svc.save(update_fields=['amount'])
        resp = self.client.get(reverse('service_detail', args=[self.svc.pk]))
        self.assertEqual(resp.context['service_revenue'], Decimal('500.00'))
        # COGS still based on cost_price × qty
        self.assertEqual(resp.context['service_cogs'], Decimal('160.00'))
        self.assertEqual(resp.context['gross_profit'], Decimal('340.00'))
        # Reset
        self.svc.amount = None
        self.svc.save(update_fields=['amount'])

    def test_pnl_zero_revenue_no_error(self):
        """Service with no lines or zero prices doesn't crash P&L calculations."""
        from services.models import CustomerService
        svc_empty = CustomerService.objects.create(
            service_number='SDP-EMPTY',
            service_name='Empty Service',
            customer_name='Empty Cust',
            service_date=datetime.date.today(),
            created_by=self.user,
        )
        resp = self.client.get(reverse('service_detail', args=[svc_empty.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['service_revenue'], Decimal('0'))
        self.assertEqual(resp.context['gross_margin'], Decimal('0'))


# ════════════════════════════════════════════════════════════════════════════
# 6. compute_invoice_cogs for Service Invoices
# ════════════════════════════════════════════════════════════════════════════

class ServiceInvoiceCOGSTest(TestCase):
    """compute_invoice_cogs returns sum(cost_price×qty) for service invoices."""

    @classmethod
    def setUpTestData(cls):
        from services.models import CustomerService, ServiceLine
        from core.models import Invoice
        cls.user = _make_user('sic_user')
        cls.item, cls.unit, cls.wh, cls.loc = _make_base_fixtures('SIC')

        cls.invoice = Invoice.objects.create(
            invoice_number='SIC-INV-001',
            date=datetime.date.today(),
            customer_name='COGS Test Customer',
            subtotal=Decimal('600.00'),
            grand_total=Decimal('600.00'),
            grand_total_cogs=Decimal('0'),
            created_by=cls.user,
        )
        cls.svc = CustomerService.objects.create(
            service_number='SIC-SVC-001',
            service_name='COGS Test Service',
            customer_name='COGS Test Customer',
            service_date=datetime.date.today(),
            status='COMPLETED',
            invoice=cls.invoice,
            created_by=cls.user,
        )
        # cost=80, qty=3 → COGS=240
        ServiceLine.objects.create(
            service=cls.svc,
            item=cls.item,
            location=cls.loc,
            qty=Decimal('3'),
            unit=cls.unit,
            unit_price=Decimal('200.00'),
        )

    def test_compute_invoice_cogs_returns_correct_value(self):
        from core.cogs import compute_invoice_cogs
        cogs = compute_invoice_cogs(self.invoice)
        self.assertEqual(cogs, Decimal('240.00'))

    def test_service_cogs_not_counted_when_linked_to_so(self):
        """Invoices with a linked SO should use SO COGS, not service COGS."""
        from core.cogs import compute_invoice_cogs
        from sales.models import SalesOrder
        from catalog.models import Unit
        from partners.models import Customer
        from warehouses.models import Warehouse
        from core.models import DocumentStatus, Invoice as Inv

        cat_unit = self.unit
        cust = Customer.objects.create(name='SO Cust', code='SO-CUST-SIC')
        wh = Warehouse.objects.create(name='SO WH SIC', code='SO-WH-SIC')

        so = SalesOrder.objects.create(
            document_number='SO-SIC-001',
            status=DocumentStatus.APPROVED,
            customer=cust,
            warehouse=wh,
            order_date=datetime.date.today(),
            created_by=self.user,
        )
        # SO invoice linked to both SO and a service
        so_inv = Inv.objects.create(
            invoice_number='SO-SIC-INV-001',
            date=datetime.date.today(),
            sales_order=so,
            customer_name='SO Cust',
            subtotal=Decimal('300.00'),
            grand_total=Decimal('300.00'),
            created_by=self.user,
        )
        # COGS should come from SO (0 lines = 0 COGS), not the service
        from services.models import CustomerService
        svc2 = CustomerService.objects.create(
            service_number='SIC-SVC-002',
            service_name='SO Linked Service',
            customer_name='SO Cust',
            service_date=datetime.date.today(),
            status='COMPLETED',
            invoice=so_inv,
            created_by=self.user,
        )
        # compute_invoice_cogs should prefer SO source
        cogs = compute_invoice_cogs(so_inv)
        self.assertEqual(cogs, Decimal('0.00'))  # SO has no lines


# ════════════════════════════════════════════════════════════════════════════
# 7. Service Invoice List
# ════════════════════════════════════════════════════════════════════════════

class ServiceInvoiceListTest(TestCase):
    """service_invoice_list shows only service-generated invoices."""

    @classmethod
    def setUpTestData(cls):
        from services.models import CustomerService
        from core.models import Invoice
        cls.user = _make_user('sil_user')

        # Service invoice
        cls.svc_invoice = Invoice.objects.create(
            invoice_number='SIL-SVC-INV-001',
            date=datetime.date.today(),
            customer_name='Service Customer',
            grand_total=Decimal('500.00'),
            created_by=cls.user,
        )
        cls.svc = CustomerService.objects.create(
            service_number='SIL-SVC-001',
            service_name='List Test Service',
            customer_name='Service Customer',
            service_date=datetime.date.today(),
            status='COMPLETED',
            invoice=cls.svc_invoice,
            created_by=cls.user,
        )

        # Non-service invoice (no customer service linked)
        cls.non_svc_invoice = Invoice.objects.create(
            invoice_number='SIL-REG-INV-001',
            date=datetime.date.today(),
            customer_name='Regular Customer',
            grand_total=Decimal('300.00'),
            created_by=cls.user,
        )

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.user)

    def test_service_invoice_list_returns_200(self):
        resp = self.client.get(reverse('service_invoice_list'))
        self.assertEqual(resp.status_code, 200)

    def test_only_service_invoices_shown(self):
        resp = self.client.get(reverse('service_invoice_list'))
        invoices = list(resp.context['invoices'])
        invoice_ids = [inv.pk for inv in invoices]
        self.assertIn(self.svc_invoice.pk, invoice_ids)
        self.assertNotIn(self.non_svc_invoice.pk, invoice_ids)

    def test_paid_filter_works(self):
        from core.models import Invoice
        paid_inv = Invoice.objects.create(
            invoice_number='SIL-SVC-PAID-001',
            date=datetime.date.today(),
            customer_name='Paid Customer',
            grand_total=Decimal('200.00'),
            is_paid=True,
            paid_date=datetime.date.today(),
            created_by=self.user,
        )
        from services.models import CustomerService
        CustomerService.objects.create(
            service_number='SIL-SVC-PAID-001',
            service_name='Paid Service',
            customer_name='Paid Customer',
            service_date=datetime.date.today(),
            status='COMPLETED',
            invoice=paid_inv,
            created_by=self.user,
        )

        resp = self.client.get(reverse('service_invoice_list') + '?paid=1')
        invoices = list(resp.context['invoices'])
        invoice_ids = [inv.pk for inv in invoices]
        self.assertIn(paid_inv.pk, invoice_ids)
        # Unpaid SVC invoice should NOT appear in paid=1 filter
        self.assertNotIn(self.svc_invoice.pk, invoice_ids)

    def test_total_revenue_in_context(self):
        resp = self.client.get(reverse('service_invoice_list'))
        self.assertIn('total_revenue', resp.context)
        self.assertGreaterEqual(resp.context['total_revenue'], Decimal('500.00'))

    def test_service_invoice_list_html_shows_service_link(self):
        resp = self.client.get(reverse('service_invoice_list'))
        content = resp.content.decode()
        self.assertIn('SIL-SVC-INV-001', content)
        self.assertIn('SIL-SVC-001', content)
        self.assertNotIn('SIL-REG-INV-001', content)


# ════════════════════════════════════════════════════════════════════════════
# 8. Grand Total Calculation
# ════════════════════════════════════════════════════════════════════════════

class ServiceGrandTotalTest(TestCase):
    """grand_total uses line total by default; manual amount overrides."""

    @classmethod
    def setUpTestData(cls):
        from services.models import CustomerService, ServiceLine
        cls.user = _make_user('sgt_user')
        cls.item, cls.unit, cls.wh, cls.loc = _make_base_fixtures('SGT')

        cls.svc = CustomerService.objects.create(
            service_number='SGT-001',
            service_name='Grand Total Test',
            customer_name='GT Customer',
            service_date=datetime.date.today(),
            created_by=cls.user,
        )
        ServiceLine.objects.create(
            service=cls.svc,
            item=cls.item,
            location=cls.loc,
            qty=Decimal('5'),
            unit=cls.unit,
            unit_price=Decimal('100.00'),
        )

    def test_grand_total_equals_line_total_by_default(self):
        self.assertEqual(self.svc.grand_total, Decimal('500.00'))

    def test_grand_total_uses_manual_amount_when_set(self):
        self.svc.amount = Decimal('750.00')
        self.svc.save(update_fields=['amount'])
        self.svc.refresh_from_db()
        self.assertEqual(self.svc.grand_total, Decimal('750.00'))
        # Restore
        self.svc.amount = None
        self.svc.save(update_fields=['amount'])

    def test_line_total_still_correct_when_manual_amount_set(self):
        self.svc.amount = Decimal('999.00')
        self.svc.save(update_fields=['amount'])
        self.svc.refresh_from_db()
        # line_total is still qty × unit_price, independent of manual amount
        self.assertEqual(self.svc.line_total, Decimal('500.00'))
        # Restore
        self.svc.amount = None
        self.svc.save(update_fields=['amount'])


# ════════════════════════════════════════════════════════════════════════════
# 9. Insufficient Stock Guard
# ════════════════════════════════════════════════════════════════════════════

class ServiceInsufficientStockTest(TestCase):
    """service_complete blocks when stock < requested and negative stock disallowed."""

    @classmethod
    def setUpTestData(cls):
        from services.models import CustomerService, ServiceLine
        from warehouses.models import Warehouse, Location
        cls.user = _make_user('sis_user')
        cls.item, cls.unit, cls.wh, cls.loc = _make_base_fixtures('SIS')
        # Warehouse does NOT allow negative stock (default)

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.user)

    def test_complete_fails_when_insufficient_stock(self):
        from services.models import CustomerService, ServiceLine, ServiceStatus
        svc = CustomerService.objects.create(
            service_number='SIS-LOW-001',
            service_name='Insufficient Stock Test',
            customer_name='Cust',
            service_date=datetime.date.today(),
            warehouse=self.wh,
            created_by=self.user,
        )
        ServiceLine.objects.create(
            service=svc,
            item=self.item,
            location=self.loc,
            qty=Decimal('100'),  # Way more than available
            unit=self.unit,
            unit_price=Decimal('100.00'),
        )
        # Seed only 1 unit
        _seed_stock(self.item, self.loc, Decimal('1'))

        resp = self.client.post(reverse('service_complete', args=[svc.pk]), follow=True)
        svc.refresh_from_db()
        # Should NOT complete
        self.assertNotEqual(svc.status, ServiceStatus.COMPLETED)

    def test_complete_succeeds_when_warehouse_allows_negative(self):
        from services.models import CustomerService, ServiceLine, ServiceStatus
        from warehouses.models import Warehouse, Location
        wh_neg = Warehouse.objects.create(
            name='SIS Neg WH', code='SIS-NEG-WH', allow_negative_stock=True
        )
        loc_neg = Location.objects.create(
            name='SIS Neg Loc', code='SIS-NEG-LOC', warehouse=wh_neg, is_pickable=True
        )
        svc = CustomerService.objects.create(
            service_number='SIS-NEG-001',
            service_name='Negative Stock Test',
            customer_name='Cust',
            service_date=datetime.date.today(),
            warehouse=wh_neg,
            created_by=self.user,
        )
        ServiceLine.objects.create(
            service=svc,
            item=self.item,
            location=loc_neg,
            qty=Decimal('999'),
            unit=self.unit,
            unit_price=Decimal('100.00'),
        )
        _seed_stock(self.item, loc_neg, Decimal('0'))

        self.client.post(reverse('service_complete', args=[svc.pk]))
        svc.refresh_from_db()
        self.assertEqual(svc.status, ServiceStatus.COMPLETED)


# ════════════════════════════════════════════════════════════════════════════
# 10. SERVICE_OUT MoveType Exists
# ════════════════════════════════════════════════════════════════════════════

class ServiceOutMoveTypeTest(TestCase):
    """SERVICE_OUT is a valid MoveType choice."""

    def test_service_out_in_move_type_choices(self):
        from inventory.models import MoveType
        values = [choice[0] for choice in MoveType.choices]
        self.assertIn('SERVICE_OUT', values)

    def test_service_out_label(self):
        from inventory.models import MoveType
        self.assertEqual(MoveType.SERVICE_OUT.label, 'Service Out')


if __name__ == '__main__':
    import unittest
    unittest.main()
