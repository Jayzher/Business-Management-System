"""
Selenium E2E Tests — Enhanced Services Module
=============================================
Tests the new features added to the Services module:
  1. Other Materials inline table (item_name, qty, unit_price, total, vendor)
  2. Service Fee field (separate from product lines)
  3. Discount field (Fixed Amount + Percentage modes)
  4. Live grand-total calculation in the form
  5. Service completion with invoice generation (COGS, ROI, PNL)
  6. Invoice detail page shows ROI/PNL card
  7. Service detail page shows Other Materials table, pricing breakdown, ROI

Run:
    python manage.py test tests.test_e2e_services_enhanced --verbosity=2
"""

import os
import time
import datetime
from decimal import Decimal

from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import override_settings
from django.contrib.auth import get_user_model
from django.urls import reverse

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC

User = get_user_model()


# ── Fixture helpers ──────────────────────────────────────────────────────────

def _make_fixtures(prefix='SE'):
    from catalog.models import Category, Item, Unit
    from warehouses.models import Warehouse, Location
    from inventory.models import StockBalance

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
    wh = Warehouse.objects.create(
        name=f'{prefix} Warehouse', code=f'{prefix}WH',
        allow_negative_stock=True,
    )
    loc = Location.objects.create(
        name=f'{prefix} Main', code=f'{prefix}MAIN', warehouse=wh, is_pickable=True,
    )
    # Seed enough stock
    StockBalance.objects.update_or_create(
        item=item, location=loc,
        defaults={'qty_on_hand': Decimal('100'), 'qty_reserved': Decimal('0')},
    )
    return item, unit, wh, loc


# ── Test class ───────────────────────────────────────────────────────────────

@override_settings(
    DEBUG=True,
    STATICFILES_STORAGE='django.contrib.staticfiles.storage.StaticFilesStorage',
)
class EnhancedServicesE2ETest(StaticLiveServerTestCase):
    """Selenium E2E tests for the enhanced Services module."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        opts = Options()
        if os.environ.get('CI') or os.environ.get('HEADLESS', '').lower() in ('1', 'true'):
            opts.add_argument('--headless=new')
        opts.add_argument('--no-sandbox')
        opts.add_argument('--disable-dev-shm-usage')
        opts.add_argument('--window-size=1400,900')

        driver_path = os.environ.get('CHROMEDRIVER_PATH')
        cls.browser = (
            webdriver.Chrome(service=ChromeService(driver_path), options=opts)
            if driver_path else webdriver.Chrome(options=opts)
        )
        cls.browser.implicitly_wait(5)
        cls.wait = WebDriverWait(cls.browser, 15)

    @classmethod
    def tearDownClass(cls):
        cls.browser.quit()
        super().tearDownClass()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def url(self, path):
        return f'{self.live_server_url}{path}'

    def login(self):
        self.browser.get(self.url('/accounts/login/'))
        self.wait.until(EC.presence_of_element_located((By.NAME, 'username')))
        self.browser.find_element(By.NAME, 'username').send_keys('svc_admin')
        self.browser.find_element(By.NAME, 'password').send_keys('pass1234')
        self.browser.execute_script(
            'arguments[0].click();',
            self.browser.find_element(By.CSS_SELECTOR, 'button[type=submit]'),
        )
        self.wait.until(EC.url_contains('/dashboard'))

    def fill(self, name, value):
        el = self.wait.until(EC.presence_of_element_located((By.NAME, name)))
        self.browser.execute_script('arguments[0].scrollIntoView(true);', el)
        el.clear()
        el.send_keys(str(value))

    def set_date(self, name, iso):
        el = self.wait.until(EC.presence_of_element_located((By.NAME, name)))
        self.browser.execute_script(
            "arguments[0].value=arguments[1];"
            "arguments[0].dispatchEvent(new Event('change',{bubbles:true}));",
            el, iso,
        )

    def select_val(self, name, value):
        el = self.wait.until(EC.presence_of_element_located((By.NAME, name)))
        self.browser.execute_script('arguments[0].scrollIntoView(true);', el)
        Select(el).select_by_value(value)

    def js_set(self, selector, value):
        el = self.browser.find_element(By.CSS_SELECTOR, selector)
        self.browser.execute_script(
            "arguments[0].value=arguments[1];"
            "arguments[0].dispatchEvent(new Event('input',{bubbles:true}));"
            "arguments[0].dispatchEvent(new Event('change',{bubbles:true}));",
            el, str(value),
        )

    def submit(self):
        btn = self.browser.find_element(By.CSS_SELECTOR, 'button[type=submit]')
        self.browser.execute_script('arguments[0].click();', btn)
        self.wait.until(lambda d: d.execute_script('return document.readyState') == 'complete')
        time.sleep(0.5)

    def assert_no_server_error(self):
        src = self.browser.page_source
        self.assertNotIn('Traceback', src, 'Server error on page')
        self.assertNotIn('Server Error (500)', src, '500 error on page')
        self.assertNotIn('Page not found', src, '404 error on page')

    def assert_present(self, text):
        self.assertIn(text, self.browser.page_source,
                      f'{text!r} not found on page {self.browser.current_url}')

    # ── setUp ─────────────────────────────────────────────────────────────────

    def setUp(self):
        self.user = User.objects.create_superuser(
            'svc_admin', 'svc@test.com', 'pass1234',
        )
        self.item, self.unit, self.wh, self.loc = _make_fixtures('SE')
        self.login()

    def tearDown(self):
        pass  # DB flushed automatically by TransactionTestCase between tests

    # ══════════════════════════════════════════════════════════════════════════
    # Step 1 — Create Service with Other Materials + Discount + Service Fee
    # ══════════════════════════════════════════════════════════════════════════

    def test_01_create_service_with_other_materials(self):
        """Create a service with one other material row and a service fee."""
        self.browser.get(self.url('/services/create/'))
        self.assert_no_server_error()

        # Fill header fields
        self.fill('service_number', 'SE-TEST-001')
        self.fill('service_name', 'AC Unit Repair')
        self.fill('customer_name', 'Test Customer')
        self.set_date('service_date', datetime.date.today().isoformat())

        # Fill Quotation
        self.js_set('#id_quotation', '800.00')

        # Fill Discount (Fixed ₱100)
        self.select_val('discount_type', 'FIXED')
        self.js_set('#id_discount_value', '100.00')

        # Add an Other Material row via the "Add Other Material" button
        add_btn = self.wait.until(
            EC.element_to_be_clickable((By.ID, 'mat-add-row'))
        )
        self.browser.execute_script('arguments[0].click();', add_btn)
        time.sleep(0.5)

        # Fill the first material row
        tbody = self.browser.find_element(By.ID, 'mat-tbody')
        rows = tbody.find_elements(By.CLASS_NAME, 'mat-row')
        self.assertGreater(len(rows), 0, 'No material rows appeared after clicking Add')

        last_row = rows[-1]
        last_row.find_element(By.CSS_SELECTOR, '[name$="-item_name"]').send_keys('Copper Wire')
        qty_el = last_row.find_element(By.CSS_SELECTOR, '.mat-qty')
        self.browser.execute_script(
            "arguments[0].value='2';"
            "arguments[0].dispatchEvent(new Event('input',{bubbles:true}));",
            qty_el,
        )
        price_el = last_row.find_element(By.CSS_SELECTOR, '.mat-price')
        self.browser.execute_script(
            "arguments[0].value='150';"
            "arguments[0].dispatchEvent(new Event('input',{bubbles:true}));",
            price_el,
        )
        last_row.find_element(By.CSS_SELECTOR, '[name$="-vendor"]').send_keys('ABC Supplies')
        time.sleep(0.4)

        # Verify row total = 2 × 150 = 300
        total_span = last_row.find_element(By.CLASS_NAME, 'mat-row-total')
        self.assertEqual(total_span.text.strip(), '300.00',
                         f'Expected row total 300.00, got {total_span.text!r}')

        # Submit
        self.submit()
        self.assert_no_server_error()
        self.assert_present('SE-TEST-001')

        # Verify Other Materials section on detail page
        self.assert_present('Other Materials')
        self.assert_present('Copper Wire')
        self.assert_present('ABC Supplies')

    # ══════════════════════════════════════════════════════════════════════════
    # Step 2 — Live Grand Total Calculation
    # ══════════════════════════════════════════════════════════════════════════

    def test_02_live_grand_total_updates(self):
        """Live totals box updates correctly: subtotal - discount = grand total."""
        self.browser.get(self.url('/services/create/'))
        self.assert_no_server_error()

        # Set quotation (3000 - mats 1000 = sub 2000)
        self.js_set('#id_quotation', '3000')
        time.sleep(0.1)

        # Set discount type = PERCENT, value = 10%
        self.select_val('discount_type', 'PERCENT')
        self.js_set('#id_discount_value', '10')
        time.sleep(0.5)

        # Add a material: qty=2, price=500 → mat total=1000
        add_btn = self.browser.find_element(By.ID, 'mat-add-row')
        self.browser.execute_script('arguments[0].click();', add_btn)
        time.sleep(0.4)

        tbody = self.browser.find_element(By.ID, 'mat-tbody')
        rows = tbody.find_elements(By.CLASS_NAME, 'mat-row')
        last = rows[-1]
        self.browser.execute_script(
            "arguments[0].value='2';"
            "arguments[0].dispatchEvent(new Event('input',{bubbles:true}));",
            last.find_element(By.CSS_SELECTOR, '.mat-qty'),
        )
        self.browser.execute_script(
            "arguments[0].value='500';"
            "arguments[0].dispatchEvent(new Event('input',{bubbles:true}));",
            last.find_element(By.CSS_SELECTOR, '.mat-price'),
        )
        time.sleep(0.6)

        # Expected: quot=3000, lines=0, mats=1000 → sub=2000, disc=200(10%), grand=1800
        grand_el = self.browser.find_element(By.ID, 'tot-grand')
        grand_text = grand_el.text.strip()
        self.assertEqual(grand_text, '1800.00',
                         f'Expected grand total 1800.00 got {grand_text!r}')

        subtotal_el = self.browser.find_element(By.ID, 'tot-subtotal')
        self.assertEqual(subtotal_el.text.strip(), '2000.00')

        discount_el = self.browser.find_element(By.ID, 'tot-discount')
        self.assertEqual(discount_el.text.strip(), '200.00')

    # ══════════════════════════════════════════════════════════════════════════
    # Step 3 — Service Fee Displayed on Detail Page
    # ══════════════════════════════════════════════════════════════════════════

    def test_03_quotation_and_discount_on_detail(self):
        """Service detail page shows quotation, discount, and grand total breakdown."""
        from services.models import CustomerService, ServiceOtherMaterial

        svc = CustomerService.objects.create(
            service_number='SE-DETAIL-001',
            service_name='Detail Test Service',
            customer_name='Detail Customer',
            service_date=datetime.date.today(),
            quotation=Decimal('1700.00'),
            discount_type='FIXED',
            discount_value=Decimal('100.00'),
            created_by=self.user,
        )
        ServiceOtherMaterial.objects.create(
            service=svc,
            item_name='Epoxy Resin',
            qty=Decimal('3'),
            unit_price=Decimal('200.00'),
            vendor='Resin Depot',
        )

        self.browser.get(self.url(f'/services/{svc.pk}/'))
        self.assert_no_server_error()

        src = self.browser.page_source
        # Other Materials table
        self.assertIn('Other Materials', src)
        self.assertIn('Epoxy Resin', src)
        self.assertIn('Resin Depot', src)

        # Pricing breakdown
        self.assertIn('Quotation', src)
        self.assertIn('Pricing Breakdown', src)
        self.assertIn('Net', src)
        self.assertIn('Discount', src)
        self.assertIn('Grand Total', src)

        # Totals: quot(1700) - mats(600) = net 1100, disc 100 → grand 1000
        self.assertIn('1,100', src)  # net contains 1,100.00
        self.assertIn('1,000', src)  # grand total contains 1,000.00

    # ══════════════════════════════════════════════════════════════════════════
    # Step 4 — Complete Service → Invoice with ROI/PNL
    # ══════════════════════════════════════════════════════════════════════════

    def test_04_complete_service_generates_invoice_with_roi(self):
        """Completing a service generates an invoice; invoice detail shows ROI/PNL."""
        from services.models import CustomerService, ServiceLine, ServiceOtherMaterial

        svc = CustomerService.objects.create(
            service_number='SE-COMP-001',
            service_name='Completion Test',
            customer_name='Comp Customer',
            service_date=datetime.date.today(),
            warehouse=self.wh,
            quotation=Decimal('1400.00'),
            discount_type='FIXED',
            discount_value=Decimal('50.00'),
            created_by=self.user,
        )
        ServiceLine.objects.create(
            service=svc,
            item=self.item,
            location=self.loc,
            qty=Decimal('2'),
            unit=self.unit,
            unit_price=Decimal('200.00'),
        )
        ServiceOtherMaterial.objects.create(
            service=svc,
            item_name='Coolant Fluid',
            qty=Decimal('1'),
            unit_price=Decimal('150.00'),
            vendor='Fluid Co',
        )

        # Navigate to service detail and complete it
        self.browser.get(self.url(f'/services/{svc.pk}/'))
        self.assert_no_server_error()

        complete_btn = self.wait.until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, 'button[onclick*="Complete this service"]')
            )
        )
        # Dismiss the confirm dialog via JS before click
        self.browser.execute_script("window.confirm = function() { return true; };")
        self.browser.execute_script('arguments[0].closest("form").submit();', complete_btn)
        time.sleep(2)
        self.wait.until(lambda d: d.execute_script('return document.readyState') == 'complete')

        svc.refresh_from_db()
        self.assertEqual(svc.status, 'COMPLETED', 'Service should be COMPLETED')
        self.assertIsNotNone(svc.invoice, 'Invoice should be generated')

        # Check service detail shows Completed badge
        self.assert_no_server_error()
        self.assert_present('Completed')
        self.assert_present('View Invoice')

        # ── Check invoice was created with correct totals ──────────────────
        inv = svc.invoice
        # quot(1400) - lines(400) - mats(150) = net 850, discount = 50, grand_total = 800
        self.assertEqual(inv.grand_total, Decimal('800.00'),
                         f'Expected grand_total 800.00, got {inv.grand_total}')
        self.assertEqual(inv.discount_total, Decimal('50.00'))

        # COGS: product line cost = 80×2=160, mat cost = 150×1=150 → total=310
        self.assertEqual(inv.grand_total_cogs, Decimal('310.00'),
                         f'Expected COGS 310.00, got {inv.grand_total_cogs}')

        # ── View invoice detail — verify ROI/PNL card ──────────────────────
        self.browser.get(self.url(f'/core/invoices/{inv.pk}/'))
        self.assert_no_server_error()

        self.assert_present('ROI')
        self.assert_present('PNL')
        self.assert_present('svc-roi-pnl-card')

        # Wait for JS to compute ROI/PNL values
        time.sleep(0.8)
        pnl_el = self.browser.find_element(By.ID, 'inv-pnl-value')
        roi_el = self.browser.find_element(By.ID, 'inv-roi-value')

        # PNL = 800 - 310 = 490
        self.assertIn('490', pnl_el.text, f'PNL should contain 490, got {pnl_el.text!r}')
        # ROI = 490/310 × 100 ≈ 158.1%
        self.assertIn('158', roi_el.text, f'ROI should contain 158, got {roi_el.text!r}')

    # ══════════════════════════════════════════════════════════════════════════
    # Step 5 — Service Detail Shows ROI in Summary Card
    # ══════════════════════════════════════════════════════════════════════════

    def test_05_service_detail_roi_in_summary_card(self):
        """After completion, service detail summary card shows ROI and PNL."""
        from services.models import CustomerService, ServiceLine, ServiceOtherMaterial, ServiceStatus
        from core.models import Invoice

        # Create a pre-completed service directly in DB
        inv = Invoice.objects.create(
            invoice_number='SE-ROI-INV-001',
            date=datetime.date.today(),
            customer_name='ROI Test Customer',
            subtotal=Decimal('700.00'),
            grand_total=Decimal('700.00'),
            grand_total_cogs=Decimal('200.00'),
            created_by=self.user,
        )
        svc = CustomerService.objects.create(
            service_number='SE-ROI-001',
            service_name='ROI Summary Test',
            customer_name='ROI Test Customer',
            service_date=datetime.date.today(),
            status=ServiceStatus.COMPLETED,
            quotation=Decimal('900.00'),
            invoice=inv,
            created_by=self.user,
        )
        ServiceLine.objects.create(
            service=svc,
            item=self.item,
            location=self.loc,
            qty=Decimal('1'),
            unit=self.unit,
            unit_price=Decimal('200.00'),
        )
        ServiceOtherMaterial.objects.create(
            service=svc,
            item_name='Sealant',
            qty=Decimal('2'),
            unit_price=Decimal('100.00'),
            vendor='Seal Co',
        )

        self.browser.get(self.url(f'/services/{svc.pk}/'))
        self.assert_no_server_error()

        src = self.browser.page_source
        self.assertIn('ROI', src)
        self.assertIn('PNL', src)
        self.assertIn('Profit &amp; Loss', src)
        # Summary card should show ROI row
        self.assertIn('Return on Investment', src)

    # ══════════════════════════════════════════════════════════════════════════
    # Step 6 — Edit Service: Other Materials persisted and editable
    # ══════════════════════════════════════════════════════════════════════════

    def test_06_edit_service_other_materials_persisted(self):
        """Edit form pre-fills existing other materials, can add more."""
        from services.models import CustomerService, ServiceOtherMaterial

        svc = CustomerService.objects.create(
            service_number='SE-EDIT-001',
            service_name='Edit Test Service',
            customer_name='Edit Customer',
            service_date=datetime.date.today(),
            created_by=self.user,
        )
        ServiceOtherMaterial.objects.create(
            service=svc,
            item_name='Existing Material',
            qty=Decimal('1'),
            unit_price=Decimal('100.00'),
            vendor='Old Vendor',
        )

        self.browser.get(self.url(f'/services/{svc.pk}/edit/'))
        self.assert_no_server_error()

        src = self.browser.page_source
        # Existing material item_name should be pre-filled
        self.assertIn('Existing Material', src)

        # Add a new row
        add_btn = self.browser.find_element(By.ID, 'mat-add-row')
        self.browser.execute_script('arguments[0].click();', add_btn)
        time.sleep(0.3)

        tbody = self.browser.find_element(By.ID, 'mat-tbody')
        rows = tbody.find_elements(By.CSS_SELECTOR, 'tr.mat-row:not([style*="display: none"])')
        new_row = rows[-1]
        new_row.find_element(By.CSS_SELECTOR, '[name$="-item_name"]').send_keys('New Material')
        self.browser.execute_script(
            "arguments[0].value='3';"
            "arguments[0].dispatchEvent(new Event('input',{bubbles:true}));",
            new_row.find_element(By.CSS_SELECTOR, '.mat-qty'),
        )
        self.browser.execute_script(
            "arguments[0].value='50';"
            "arguments[0].dispatchEvent(new Event('input',{bubbles:true}));",
            new_row.find_element(By.CSS_SELECTOR, '.mat-price'),
        )

        self.submit()
        self.assert_no_server_error()

        # Both materials should show on detail
        self.assert_present('Existing Material')
        self.assert_present('New Material')

    # ══════════════════════════════════════════════════════════════════════════
    # Step 7 — Percentage Discount Calculation
    # ══════════════════════════════════════════════════════════════════════════

    def test_07_percentage_discount_stored_and_displayed(self):
        """Service with PERCENT discount shows correct grand total on detail."""
        from services.models import CustomerService, ServiceLine, ServiceOtherMaterial

        # quot(1400) - lines(400) - mats(300) = net 700
        # discount = 10% of 700 = 70
        # grand total = 630
        svc = CustomerService.objects.create(
            service_number='SE-DISC-001',
            service_name='Discount Test',
            customer_name='Disc Customer',
            service_date=datetime.date.today(),
            quotation=Decimal('1400.00'),
            discount_type='PERCENT',
            discount_value=Decimal('10.00'),
            created_by=self.user,
        )
        ServiceLine.objects.create(
            service=svc,
            item=self.item,
            location=self.loc,
            qty=Decimal('2'),
            unit=self.unit,
            unit_price=Decimal('200.00'),
        )
        ServiceOtherMaterial.objects.create(
            service=svc,
            item_name='Tape Roll',
            qty=Decimal('3'),
            unit_price=Decimal('100.00'),
            vendor='Tape Inc',
        )

        self.browser.get(self.url(f'/services/{svc.pk}/'))
        self.assert_no_server_error()

        src = self.browser.page_source
        self.assertIn('Percentage', src)
        self.assertIn('630', src)  # grand total 630.00

    # ══════════════════════════════════════════════════════════════════════════
    # Step 8 — Invoice Lines Include All Three Types
    # ══════════════════════════════════════════════════════════════════════════

    def test_08_invoice_lines_contain_all_types(self):
        """Completed service invoice has product line, material line, and fee line."""
        from services.models import CustomerService, ServiceLine, ServiceOtherMaterial
        from core.models import InvoiceLine

        svc = CustomerService.objects.create(
            service_number='SE-INV-001',
            service_name='Full Invoice Test',
            customer_name='Full Invoice Cust',
            service_date=datetime.date.today(),
            warehouse=self.wh,
            quotation=Decimal('500.00'),
            discount_type='FIXED',
            discount_value=Decimal('0.00'),
            created_by=self.user,
        )
        ServiceLine.objects.create(
            service=svc,
            item=self.item,
            location=self.loc,
            qty=Decimal('1'),
            unit=self.unit,
            unit_price=Decimal('200.00'),
        )
        ServiceOtherMaterial.objects.create(
            service=svc,
            item_name='Test Material',
            qty=Decimal('1'),
            unit_price=Decimal('100.00'),
            vendor='TestVendor',
        )

        # Complete via POST
        from django.test import Client
        client = Client()
        client.force_login(self.user)
        response = client.post(reverse('service_complete', args=[svc.pk]), follow=True)
        svc.refresh_from_db()
        self.assertEqual(svc.status, 'COMPLETED')

        inv = svc.invoice
        lines = list(inv.lines.all())
        item_codes = [l.item_code for l in lines]

        # Should have product line (item code), material line (MAT), and quotation line (SVC-QUOT)
        self.assertIn(self.item.code, item_codes, 'Product line should be in invoice')
        self.assertIn('MAT', item_codes, 'Other material line should be in invoice')
        self.assertIn('SVC-QUOT', item_codes, 'Quotation line should be in invoice')

        # grand_total_cogs = product line COGS (80×1=80) + mat cost (100×1=100) = 180
        self.assertEqual(inv.grand_total_cogs, Decimal('180.00'),
                         f'COGS should be 180.00, got {inv.grand_total_cogs}')

    # ══════════════════════════════════════════════════════════════════════════
    # Step 9 — Unit Test: Model Properties
    # ══════════════════════════════════════════════════════════════════════════

    def test_09_model_grand_total_properties(self):
        """Model properties: subtotal, discount_amount, grand_total compute correctly."""
        from services.models import CustomerService, ServiceLine, ServiceOtherMaterial

        svc = CustomerService.objects.create(
            service_number='SE-MODEL-001',
            service_name='Model Test',
            customer_name='Model Cust',
            service_date=datetime.date.today(),
            quotation=Decimal('1700.00'),
            discount_type='PERCENT',
            discount_value=Decimal('20.00'),
            created_by=self.user,
        )
        ServiceLine.objects.create(
            service=svc,
            item=self.item,
            location=self.loc,
            qty=Decimal('2'),
            unit=self.unit,
            unit_price=Decimal('200.00'),
        )
        ServiceOtherMaterial.objects.create(
            service=svc,
            item_name='Paint',
            qty=Decimal('4'),
            unit_price=Decimal('50.00'),
            vendor='Paint Co',
        )

        # product_lines = 2×200 = 400
        self.assertEqual(svc.product_lines_total, Decimal('400.00'))
        # other_materials = 4×50 = 200
        self.assertEqual(svc.other_materials_total, Decimal('200.00'))
        # quotation = 1700
        self.assertEqual(svc.quotation_amount, Decimal('1700.00'))
        # subtotal = 1700 - 400 - 200 = 1100
        self.assertEqual(svc.subtotal, Decimal('1100.00'))
        # discount = 20% of 1100 = 220
        self.assertEqual(svc.discount_amount, Decimal('220.00'))
        # grand_total = 1100 - 220 = 880
        self.assertEqual(svc.grand_total, Decimal('880.00'))

    # ══════════════════════════════════════════════════════════════════════════
    # Step 10 — Fixed Discount Model Test
    # ══════════════════════════════════════════════════════════════════════════

    def test_10_fixed_discount_model(self):
        """Model: FIXED discount type deducts fixed amount."""
        from services.models import CustomerService, ServiceOtherMaterial

        svc = CustomerService.objects.create(
            service_number='SE-FD-001',
            service_name='Fixed Discount Test',
            customer_name='FD Cust',
            service_date=datetime.date.today(),
            quotation=Decimal('1000.00'),
            discount_type='FIXED',
            discount_value=Decimal('150.00'),
            created_by=self.user,
        )
        # quot=1000 - lines=0 - mats=0 = subtotal 1000, discount = 150, grand = 850
        self.assertEqual(svc.subtotal, Decimal('1000.00'))
        self.assertEqual(svc.discount_amount, Decimal('150.00'))
        self.assertEqual(svc.grand_total, Decimal('850.00'))
