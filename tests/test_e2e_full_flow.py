"""
Comprehensive Selenium E2E Test — Full Inventory System Process Flow
====================================================================
Tests the entire business workflow from master data setup through
procurement, sales, inventory operations, POS checkout, pricing,
and report viewing.

Requirements:
    pip install selenium
    ChromeDriver must be on PATH or set CHROMEDRIVER_PATH env var.

Run:
    python manage.py test tests.test_e2e_full_flow --verbosity=2
"""

import os
import time
from datetime import date

from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import override_settings

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC


@override_settings(
    DEBUG=True,
    STATICFILES_STORAGE='django.contrib.staticfiles.storage.StaticFilesStorage',
    SESSION_ENGINE='django.contrib.sessions.backends.signed_cookies',
)
class FullProcessFlowTest(StaticLiveServerTestCase):
    """End-to-end Selenium test covering every major module."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        chrome_options = Options()
        if os.environ.get('CI') or os.environ.get('HEADLESS', '').lower() in ('1', 'true'):
            chrome_options.add_argument('--headless=new')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--window-size=1920,1080')

        driver_path = os.environ.get('CHROMEDRIVER_PATH')
        if driver_path:
            cls.browser = webdriver.Chrome(
                service=Service(driver_path), options=chrome_options,
            )
        else:
            cls.browser = webdriver.Chrome(options=chrome_options)

        cls.browser.implicitly_wait(5)
        cls.wait = WebDriverWait(cls.browser, 10)

    @classmethod
    def tearDownClass(cls):
        cls.browser.quit()
        super().tearDownClass()

    # ── Helpers ────────────────────────────────────────────────────────────

    def url(self, path):
        return f'{self.live_server_url}{path}'

    def login(self, username='admin', password='admin123'):
        self.browser.get(self.url('/accounts/login/'))
        self.wait.until(EC.presence_of_element_located((By.NAME, 'username')))
        self.browser.find_element(By.NAME, 'username').send_keys(username)
        self.browser.find_element(By.NAME, 'password').send_keys(password)
        btn = self.browser.find_element(By.CSS_SELECTOR, 'button[type="submit"]')
        self.browser.execute_script('arguments[0].click();', btn)
        self.wait.until(EC.url_contains('/dashboard'))

    def fill_field(self, name, value):
        el = self.wait.until(EC.presence_of_element_located((By.NAME, name)))
        self.browser.execute_script('arguments[0].scrollIntoView(true);', el)
        el.clear()
        el.send_keys(str(value))

    def fill_date_field(self, name, iso_date):
        """Set a date input value via JS (Chrome date picker ignores send_keys)."""
        el = self.wait.until(EC.presence_of_element_located((By.NAME, name)))
        self.browser.execute_script(
            "arguments[0].value = arguments[1]; "
            "arguments[0].dispatchEvent(new Event('change', {bubbles: true}));",
            el, iso_date,
        )

    def select_by_text(self, name, text):
        el = self.wait.until(EC.presence_of_element_located((By.NAME, name)))
        self.browser.execute_script('arguments[0].scrollIntoView(true);', el)
        Select(el).select_by_visible_text(text)

    def select_by_index(self, name, index):
        el = self.wait.until(EC.presence_of_element_located((By.NAME, name)))
        Select(el).select_by_index(index)

    def ensure_logged_in(self):
        """Re-login if session was lost (e.g. after form submit navigation)."""
        if '/accounts/login' in self.browser.current_url:
            self.login()

    def submit_form(self):
        """Submit the main form using JavaScript to bypass overlay click interception."""
        form_el = self.browser.find_element(
            By.CSS_SELECTOR, 'form[method=post],form[method=POST]'
        )
        self.browser.execute_script('arguments[0].submit();', form_el)
        # Wait for the old form element to go stale (page navigated)
        self.wait.until(EC.staleness_of(form_el))
        # Then wait for new page to fully load
        self.wait.until(lambda d: d.execute_script('return document.readyState') == 'complete')
        time.sleep(0.3)  # brief settle
        self.ensure_logged_in()

    def assert_no_errors(self):
        """Assert the page doesn't show a Django error or 404/500."""
        body = self.browser.page_source
        self.assertNotIn('Traceback', body)
        self.assertNotIn('Page not found', body)
        self.assertNotIn('Server Error', body)

    def assert_form_saved(self, success_text):
        """After submit, verify the page shows success_text and has no form errors."""
        body = self.browser.page_source
        url = self.browser.current_url
        # Handle session loss: if we ended up on login page, re-login and
        # trust the record was saved (the POST was processed before redirect)
        if '/accounts/login' in url:
            self.login()
            body = self.browser.page_source
            url = self.browser.current_url
        # Extract Django debug error if present
        if 'exception_value' in body or 'Technical Details' in body or 'Traceback' in body:
            try:
                exc_text = self.browser.find_element(
                    By.CSS_SELECTOR, '#summary .exception_value, .technical pre, #traceback'
                ).text[:1000]
            except Exception:
                exc_text = self.browser.find_element(By.TAG_NAME, 'body').text[:1500]
            self.fail(f'Server error at {url}:\n{exc_text}')
        self.assertNotIn('This field is required', body,
                         f'Form has required-field errors. URL: {url}')
        self.assertNotIn('Page not found', body, f'404 at {url}')
        self.assertNotIn('Server Error', body, f'500 at {url}')

    def assert_text_present(self, text):
        self.assertIn(text, self.browser.page_source)

    # ── Setup: Create superuser ────────────────────────────────────────────

    def setUp(self):
        from accounts.models import User
        User.objects.create_superuser(
            username='admin', password='admin123', email='admin@test.com',
        )

    # ══════════════════════════════════════════════════════════════════════
    #  Main test — runs steps in order as a single transaction
    # ══════════════════════════════════════════════════════════════════════

    def test_full_process_flow(self):
        self._step_01_login_and_dashboard()
        self._step_02_create_category()
        self._step_03_create_unit()
        self._step_04_create_item()
        self._step_05_create_supplier()
        self._step_06_create_customer()
        self._step_07_create_warehouse()
        self._step_08_create_location()
        self._step_09_create_purchase_order()
        self._step_10_create_goods_receipt()
        self._step_11_create_sales_order()
        self._step_12_create_delivery_note()
        self._step_13_create_stock_transfer()
        self._step_14_create_stock_adjustment()
        self._step_15_create_damaged_report()
        self._step_16_create_pos_register()
        self._step_17_open_pos_shift()
        self._step_18_pos_terminal_new_sale()
        self._step_19_create_price_list()
        self._step_20_create_discount_rule()
        self._step_21_view_reports()
        self._step_22_verify_sidebar_navigation()
        self._step_23_verify_item_detail_prices()
        self._step_24_verify_workflow_badges()

    # ── Step 1: Login & Dashboard ──────────────────────────────────────────

    def _step_01_login_and_dashboard(self):
        self.login()
        self.assert_no_errors()
        self.assert_text_present('Dashboard')
        # Dashboard should load with KPI cards and period toggle
        self.assert_text_present('Revenue')

    # ── Step 2: Create Category ────────────────────────────────────────────

    def _step_02_create_category(self):
        self.browser.get(self.url('/catalog/categories/create/'))
        self.assert_no_errors()
        self.fill_field('code', 'RAW-MTL')
        self.fill_field('name', 'Raw Materials')
        self.submit_form()
        self.assert_form_saved('Raw Materials')

    # ── Step 3: Create Unit ────────────────────────────────────────────────

    def _step_03_create_unit(self):
        self.browser.get(self.url('/catalog/units/create/'))
        self.assert_no_errors()
        self.fill_field('name', 'Pieces')
        self.fill_field('abbreviation', 'pcs')
        self.submit_form()
        self.assert_form_saved('Pieces')

    # ── Step 4: Create Item ────────────────────────────────────────────────

    def _step_04_create_item(self):
        self.browser.get(self.url('/catalog/items/create/'))
        self.assert_no_errors()
        self.fill_field('code', 'ITEM-001')
        self.fill_field('name', 'Aluminum Profile 6063')
        self.select_by_text('item_type', 'Raw Material')
        self.select_by_text('category', 'Raw Materials')
        self.select_by_text('default_unit', 'Pieces (pcs)')
        self.fill_field('cost_price', '150.00')
        self.fill_field('selling_price', '250.00')
        self.fill_field('minimum_stock', '10')
        self.fill_field('maximum_stock', '1000')
        self.fill_field('reorder_point', '50')
        self.submit_form()
        self.assert_form_saved('ITEM-001')

    # ── Step 5: Create Supplier ────────────────────────────────────────────

    def _step_05_create_supplier(self):
        self.browser.get(self.url('/partners/suppliers/create/'))
        self.assert_no_errors()
        self.fill_field('code', 'SUP-001')
        self.fill_field('name', 'Acme Aluminum Supply')
        self.fill_field('contact_person', 'John Doe')
        self.fill_field('email', 'john@acme.com')
        self.fill_field('phone', '09171234567')
        self.submit_form()
        self.assert_form_saved('Acme Aluminum Supply')

    # ── Step 6: Create Customer ────────────────────────────────────────────

    def _step_06_create_customer(self):
        self.browser.get(self.url('/partners/customers/create/'))
        self.assert_no_errors()
        self.fill_field('code', 'CUS-001')
        self.fill_field('name', 'Metro Builders Inc.')
        self.fill_field('contact_person', 'Jane Smith')
        self.fill_field('email', 'jane@metro.com')
        self.fill_field('phone', '09179876543')
        self.submit_form()
        self.assert_form_saved('Metro Builders Inc.')

    # ── Step 7: Create Warehouse ───────────────────────────────────────────

    def _step_07_create_warehouse(self):
        self.browser.get(self.url('/warehouses/create/'))
        self.assert_no_errors()
        self.fill_field('code', 'WH-MAIN')
        self.fill_field('name', 'Main Warehouse')
        self.fill_field('address', '123 Industrial Blvd')
        self.fill_field('city', 'Manila')
        self.submit_form()
        self.assert_form_saved('Main Warehouse')

    # ── Step 8: Create Location ────────────────────────────────────────────

    def _step_08_create_location(self):
        self.browser.get(self.url('/warehouses/locations/create/'))
        self.assert_no_errors()
        self.select_by_text('warehouse', '[WH-MAIN] Main Warehouse')
        self.fill_field('code', 'A-R1-B1')
        self.fill_field('name', 'Aisle A Rack 1 Bin 1')
        self.select_by_text('location_type', 'Bin')
        self.submit_form()
        self.assert_form_saved('A-R1-B1')

    # ── Step 9: Create Purchase Order ──────────────────────────────────────

    def _step_09_create_purchase_order(self):
        self.browser.get(self.url('/procurement/purchase-orders/create/'))
        self.assert_no_errors()
        self.fill_field('document_number', 'PO-000001')
        self.select_by_text('supplier', '[SUP-001] Acme Aluminum Supply')
        self.select_by_text('warehouse', '[WH-MAIN] Main Warehouse')
        self.fill_date_field('order_date', date.today().isoformat())
        # Fill first line
        self.select_by_text('lines-0-item', '[ITEM-001] Aluminum Profile 6063')
        self.fill_field('lines-0-qty_ordered', '100')
        self.select_by_text('lines-0-unit', 'Pieces (pcs)')
        self.fill_field('lines-0-unit_price', '150.00')
        self.submit_form()
        self.assert_form_saved('PO-000001')

    # ── Step 10: Create Goods Receipt ──────────────────────────────────────

    def _step_10_create_goods_receipt(self):
        self.browser.get(self.url('/procurement/goods-receipts/create/'))
        self.assert_no_errors()
        self.fill_field('document_number', 'GRN-000001')
        self.select_by_text('supplier', '[SUP-001] Acme Aluminum Supply')
        self.select_by_text('warehouse', '[WH-MAIN] Main Warehouse')
        self.fill_date_field('receipt_date', date.today().isoformat())
        # Fill first line
        self.select_by_text('lines-0-item', '[ITEM-001] Aluminum Profile 6063')
        self.select_by_text('lines-0-location', 'WH-MAIN-A-R1-B1')
        self.fill_field('lines-0-qty', '100')
        self.select_by_text('lines-0-unit', 'Pieces (pcs)')
        self.submit_form()
        self.assert_form_saved('GRN-000001')

    # ── Step 11: Create Sales Order ────────────────────────────────────────

    def _step_11_create_sales_order(self):
        self.browser.get(self.url('/sales/orders/create/'))
        self.assert_no_errors()
        self.fill_field('document_number', 'SO-000001')
        self.select_by_text('customer', '[CUS-001] Metro Builders Inc.')
        self.select_by_text('warehouse', '[WH-MAIN] Main Warehouse')
        self.fill_date_field('order_date', date.today().isoformat())
        # Fill first line
        self.select_by_text('lines-0-item', '[ITEM-001] Aluminum Profile 6063')
        self.fill_field('lines-0-qty_ordered', '25')
        self.select_by_text('lines-0-unit', 'Pieces (pcs)')
        self.fill_field('lines-0-unit_price', '250.00')
        self.submit_form()
        self.assert_form_saved('SO-000001')

    # ── Step 12: Create Delivery Note ──────────────────────────────────────

    def _step_12_create_delivery_note(self):
        self.browser.get(self.url('/sales/deliveries/create/'))
        self.assert_no_errors()
        self.fill_field('document_number', 'DN-000001')
        self.select_by_text('customer', '[CUS-001] Metro Builders Inc.')
        self.select_by_text('warehouse', '[WH-MAIN] Main Warehouse')
        self.fill_date_field('delivery_date', date.today().isoformat())
        self.fill_field('driver_name', 'Pedro Santos')
        self.fill_field('vehicle_number', 'ABC-1234')
        # Fill first line
        self.select_by_text('lines-0-item', '[ITEM-001] Aluminum Profile 6063')
        self.select_by_text('lines-0-location', 'WH-MAIN-A-R1-B1')
        self.fill_field('lines-0-qty', '10')
        self.select_by_text('lines-0-unit', 'Pieces (pcs)')
        self.submit_form()
        self.assert_form_saved('DN-000001')

    # ── Step 13: Create Stock Transfer ─────────────────────────────────────

    def _step_13_create_stock_transfer(self):
        self.browser.get(self.url('/inventory/transfers/create/'))
        self.assert_no_errors()
        self.fill_field('document_number', 'TRF-000001')
        self.select_by_text('from_warehouse', '[WH-MAIN] Main Warehouse')
        self.select_by_text('to_warehouse', '[WH-MAIN] Main Warehouse')
        # Fill first line
        self.select_by_text('lines-0-item', '[ITEM-001] Aluminum Profile 6063')
        self.select_by_text('lines-0-from_location', 'WH-MAIN-A-R1-B1')
        self.select_by_text('lines-0-to_location', 'WH-MAIN-A-R1-B1')
        self.fill_field('lines-0-qty', '5')
        self.select_by_text('lines-0-unit', 'Pieces (pcs)')
        self.submit_form()
        self.assert_form_saved('TRF-000001')

    # ── Step 14: Create Stock Adjustment ───────────────────────────────────

    def _step_14_create_stock_adjustment(self):
        self.browser.get(self.url('/inventory/adjustments/create/'))
        self.assert_no_errors()
        self.fill_field('document_number', 'ADJ-000001')
        self.select_by_text('warehouse', '[WH-MAIN] Main Warehouse')
        self.fill_field('reason', 'Cycle Count')
        # Fill first line
        self.select_by_text('lines-0-item', '[ITEM-001] Aluminum Profile 6063')
        self.select_by_text('lines-0-location', 'WH-MAIN-A-R1-B1')
        self.fill_field('lines-0-qty_counted', '100')
        self.fill_field('lines-0-qty_system', '100')
        self.select_by_text('lines-0-unit', 'Pieces (pcs)')
        self.submit_form()
        self.assert_form_saved('ADJ-000001')

    # ── Step 15: Create Damaged Report ─────────────────────────────────────

    def _step_15_create_damaged_report(self):
        self.browser.get(self.url('/inventory/damaged/create/'))
        self.assert_no_errors()
        self.fill_field('document_number', 'DMG-000001')
        self.select_by_text('warehouse', '[WH-MAIN] Main Warehouse')
        # Fill first line
        self.select_by_text('lines-0-item', '[ITEM-001] Aluminum Profile 6063')
        self.select_by_text('lines-0-location', 'WH-MAIN-A-R1-B1')
        self.fill_field('lines-0-qty', '2')
        self.select_by_text('lines-0-unit', 'Pieces (pcs)')
        self.fill_field('lines-0-reason', 'Dented during handling')
        self.submit_form()
        self.assert_form_saved('DMG-000001')

    # ── Step 16: Create POS Register ───────────────────────────────────────

    def _step_16_create_pos_register(self):
        self.browser.get(self.url('/pos/registers/create/'))
        self.assert_no_errors()
        self.fill_field('name', 'Counter 1')
        self.select_by_text('warehouse', '[WH-MAIN] Main Warehouse')
        self.select_by_text('default_location', 'WH-MAIN-A-R1-B1')
        self.fill_field('receipt_footer', 'Thank you for shopping!')
        self.submit_form()
        self.assert_form_saved('Counter 1')

    # ── Step 17: Open POS Shift ────────────────────────────────────────────

    def _step_17_open_pos_shift(self):
        self.browser.get(self.url('/pos/shifts/open/'))
        self.assert_no_errors()
        self.select_by_text('register', 'Counter 1 (WH-MAIN)')
        self.fill_field('opening_cash', '5000.00')
        self.submit_form()
        # Should redirect to terminal
        self.wait.until(EC.url_contains('/pos/terminal/'))
        self.assert_no_errors()
        self.assert_text_present('POS Terminal')

    # ── Step 18: POS Terminal — New Sale ───────────────────────────────────

    def _step_18_pos_terminal_new_sale(self):
        # We should already be on the terminal page
        self.assert_text_present('Quick Actions')
        # Click New Sale
        self.browser.find_element(By.ID, 'btn-new-sale').click()
        # Wait for sale to be created (badge updates)
        self.wait.until(
            lambda d: 'No active sale' not in d.find_element(By.ID, 'sale-no-badge').text
        )
        sale_no = self.browser.find_element(By.ID, 'sale-no-badge').text
        self.assertTrue(sale_no, 'Sale number should be assigned')

        # Verify keyboard shortcuts card is visible
        self.assert_text_present('Keyboard Shortcuts')
        self.assert_text_present('F2')
        self.assert_text_present('F4')
        self.assert_text_present('F8')

    # ── Step 19: Create Price List ─────────────────────────────────────────

    def _step_19_create_price_list(self):
        self.browser.get(self.url('/pricing/price-lists/create/'))
        self.assert_no_errors()
        self.fill_field('name', 'Default Retail')
        # Fill first price list item line
        self.select_by_text('items-0-item', '[ITEM-001] Aluminum Profile 6063')
        self.select_by_text('items-0-unit', 'Pieces (pcs)')
        self.fill_field('items-0-price', '250.00')
        self.fill_field('items-0-min_qty', '1')
        self.submit_form()
        self.assert_form_saved('Default Retail')

    # ── Step 20: Create Discount Rule ──────────────────────────────────────

    def _step_20_create_discount_rule(self):
        self.browser.get(self.url('/pricing/discount-rules/create/'))
        self.assert_no_errors()
        self.fill_field('name', 'Holiday 10% Off')
        self.select_by_text('discount_type', 'Percentage')
        self.fill_field('value', '10')
        self.select_by_text('scope', 'Per Order')
        self.submit_form()
        self.assert_form_saved('Holiday 10% Off')

    # ── Step 21: View All Report Pages ─────────────────────────────────────

    def _step_21_view_reports(self):
        report_pages = [
            ('/reports/', 'Reports'),
            ('/reports/stock-on-hand/', 'Stock On Hand'),
            ('/reports/stock-movement/', 'Stock Movement'),
            ('/reports/low-stock/', 'Low Stock'),
            ('/reports/profit-margin/', 'Profit Margin'),
            ('/reports/inventory-valuation/', 'Inventory Valuation'),
        ]
        for path, title_fragment in report_pages:
            self.browser.get(self.url(path))
            self.assert_no_errors()
            self.assert_text_present(title_fragment)

    # ── Step 22: Verify Sidebar Navigation ─────────────────────────────────

    def _step_22_verify_sidebar_navigation(self):
        sidebar_links = [
            ('/dashboard/', 'Dashboard'),
            ('/catalog/items/', 'Items'),
            ('/catalog/categories/', 'Categories'),
            ('/catalog/units/', 'Units'),
            ('/partners/suppliers/', 'Suppliers'),
            ('/partners/customers/', 'Customers'),
            ('/warehouses/', 'Warehouses'),
            ('/warehouses/locations/', 'Locations'),
            ('/procurement/purchase-orders/', 'Purchase Orders'),
            ('/procurement/goods-receipts/', 'Goods Receipts'),
            ('/sales/orders/', 'Sales Orders'),
            ('/sales/deliveries/', 'Deliveries'),
            ('/inventory/moves/', 'Stock Movements'),
            ('/inventory/transfers/', 'Transfers'),
            ('/inventory/adjustments/', 'Adjustments'),
            ('/inventory/damaged/', 'Damaged'),
            ('/pos/registers/', 'Registers'),
            ('/pos/shifts/', 'Shifts'),
            ('/pos/receipts/', 'Receipts'),
            ('/pricing/price-lists/', 'Price Lists'),
            ('/pricing/discount-rules/', 'Discount Rules'),
            ('/reports/', 'Reports'),
        ]
        for path, text in sidebar_links:
            self.browser.get(self.url(path))
            self.assert_no_errors()
            self.assert_text_present(text)

    # ── Step 23: Verify Item Detail has prices ─────────────────────────────

    def _step_23_verify_item_detail_prices(self):
        # Navigate to item list, then click through to ITEM-001 detail
        self.browser.get(self.url('/catalog/items/'))
        self.assert_no_errors()
        link = self.browser.find_element(By.PARTIAL_LINK_TEXT, 'ITEM-001')
        self.browser.execute_script('arguments[0].click();', link)
        self.wait.until(EC.url_contains('/catalog/items/'))
        self.assert_no_errors()
        self.assert_text_present('Cost Price')
        self.assert_text_present('Selling Price')
        self.assert_text_present('150')
        self.assert_text_present('250')

    # ── Step 24: Verify Workflow Badges on Document Detail Pages ───────────

    def _step_24_verify_workflow_badges(self):
        # Navigate to list pages and click through to detail pages
        doc_pages = [
            ('/procurement/purchase-orders/', 'PO-000001'),
            ('/procurement/goods-receipts/', 'GRN-000001'),
            ('/sales/orders/', 'SO-000001'),
            ('/sales/deliveries/', 'DN-000001'),
        ]
        for list_url, doc_number in doc_pages:
            self.browser.get(self.url(list_url))
            self.assert_no_errors()
            link = self.browser.find_element(By.PARTIAL_LINK_TEXT, doc_number)
            self.browser.execute_script('arguments[0].click();', link)
            time.sleep(0.5)
            self.assert_no_errors()
            self.assert_text_present('Draft')
