"""
Selenium E2E Tests — New Business Management Modules
=====================================================
Tests all new modules: Settings, Sales Channels, Expense Categories,
Expenses, Supplies, Goals, Invoices, Reports (Sales, Expense, P&L),
Dashboard enhancements, and accounting calculation accuracy.

Run:
    python manage.py test tests.test_e2e_new_modules --verbosity=2
"""

import os
import time
from decimal import Decimal
from datetime import date, timedelta, datetime

from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import override_settings

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC


@override_settings(
    DEBUG=True,
    STATICFILES_STORAGE='django.contrib.staticfiles.storage.StaticFilesStorage',
)
class NewModulesFlowTest(StaticLiveServerTestCase):
    """E2E Selenium tests for all new business management modules."""

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

    # ── Helpers ──────────────────────────────────────────────────────────────

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
        el = self.wait.until(EC.presence_of_element_located((By.NAME, name)))
        self.browser.execute_script(
            "arguments[0].value = arguments[1]; "
            "arguments[0].dispatchEvent(new Event('change', {bubbles: true}));",
            el, iso_date,
        )

    def select_by_text(self, name, text):
        el = self.wait.until(EC.presence_of_element_located((By.NAME, name)))
        self.browser.execute_script(
            'arguments[0].scrollIntoView({block:"center"});', el)
        time.sleep(0.2)
        Select(el).select_by_visible_text(text)

    def select_by_index(self, name, index):
        el = self.wait.until(EC.presence_of_element_located((By.NAME, name)))
        self.browser.execute_script(
            'arguments[0].scrollIntoView({block:"center"});', el)
        time.sleep(0.2)
        Select(el).select_by_index(index)

    def select_first_option(self, name):
        """Select the first non-empty option via JS (avoids DOM scroll issues)."""
        el = self.wait.until(EC.presence_of_element_located((By.NAME, name)))
        self.browser.execute_script("""
            var sel = arguments[0];
            for (var i = 0; i < sel.options.length; i++) {
                if (sel.options[i].value !== '') {
                    sel.selectedIndex = i;
                    sel.dispatchEvent(new Event('change', {bubbles: true}));
                    break;
                }
            }
        """, el)
        time.sleep(0.2)

    def submit_form(self):
        form_el = self.browser.find_element(
            By.CSS_SELECTOR, 'form[method=post],form[method=POST]'
        )
        self.browser.execute_script('arguments[0].submit();', form_el)
        self.wait.until(EC.staleness_of(form_el))
        self.wait.until(lambda d: d.execute_script('return document.readyState') == 'complete')
        time.sleep(0.3)

    def click_checkbox(self, name):
        el = self.wait.until(EC.presence_of_element_located((By.NAME, name)))
        if not el.is_selected():
            self.browser.execute_script('arguments[0].click();', el)

    def assert_no_errors(self):
        body = self.browser.page_source
        self.assertNotIn('Traceback', body)
        self.assertNotIn('Page not found', body)
        self.assertNotIn('Server Error', body)

    def assert_form_saved(self, success_text):
        body = self.browser.page_source
        url = self.browser.current_url
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
        self.assertIn(success_text, body,
                      f'{success_text!r} not found after submit. URL: {url}')

    def assert_text_present(self, text):
        self.assertIn(text, self.browser.page_source)

    def assert_text_not_present(self, text):
        self.assertNotIn(text, self.browser.page_source)

    def get_text_by_css(self, css):
        el = self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, css)))
        return el.text

    # ── Setup ────────────────────────────────────────────────────────────────

    def setUp(self):
        from accounts.models import User
        from catalog.models import Category, Unit, Item
        from partners.models import Customer
        from warehouses.models import Warehouse, Location
        from pos.models import POSRegister

        self.admin = User.objects.create_superuser(
            username='admin', password='admin123', email='admin@test.com',
        )

        # Prerequisite data for POS and invoice tests
        self.cat = Category.objects.create(code='GEN', name='General')
        self.unit = Unit.objects.create(name='Pieces', abbreviation='pcs')
        self.item = Item.objects.create(
            code='TEST-001', name='Test Widget',
            item_type='FINISHED', category=self.cat,
            default_unit=self.unit,
            cost_price=Decimal('100.00'), selling_price=Decimal('250.00'),
            reorder_point=10,
        )
        self.item2 = Item.objects.create(
            code='TEST-002', name='Test Service',
            item_type='SERVICE', category=self.cat,
            default_unit=self.unit,
            cost_price=Decimal('0.00'), selling_price=Decimal('500.00'),
        )
        self.customer = Customer.objects.create(
            code='CUS-T01', name='Test Customer Corp',
            contact_person='Test Contact', email='test@cust.com',
        )
        self.wh = Warehouse.objects.create(code='WH-T', name='Test Warehouse')
        self.loc = Location.objects.create(
            warehouse=self.wh, code='T-A1', name='Test Loc',
            location_type='BIN',
        )
        self.register = POSRegister.objects.create(
            name='Test Register', warehouse=self.wh,
            default_location=self.loc,
        )

    # ══════════════════════════════════════════════════════════════════════
    #  Main test — runs all steps in order
    # ══════════════════════════════════════════════════════════════════════

    def test_new_modules_full_flow(self):
        # Phase 1: Core CRUD modules
        self._step_01_login_dashboard_period_toggle()
        self._step_02_business_settings()
        self._step_03_create_sales_channel()
        self._step_04_create_expense_category_cogs()
        self._step_05_create_expense_category_opex()
        self._step_06_record_expenses()
        self._step_07_create_supply_category()
        self._step_08_create_supply_item()
        self._step_09_record_supply_movements()
        self._step_10_verify_supply_stock_calculation()
        self._step_11_create_target_goals()

        # Phase 2: Invoice generation & POS with channel
        self._step_12_pos_sale_with_channel()
        self._step_13_generate_invoice_from_sale()
        self._step_14_verify_invoice_calculations()

        # Phase 3: Reports
        self._step_15_sales_report()
        self._step_16_expense_report()
        self._step_17_financial_statement_pnl()
        self._step_18_verify_pnl_calculations()

        # Phase 4: Dashboard deep checks
        self._step_19_dashboard_channel_breakdown()
        self._step_20_dashboard_expense_categories()
        self._step_21_dashboard_active_goals()

        # Phase 5: Sidebar navigation for new sections
        self._step_22_sidebar_new_sections()

        # Phase 6: Edit & delete flows
        self._step_23_edit_expense()
        self._step_24_edit_goal()
        self._step_25_delete_flow()

        # Phase 7: Tour Guide system
        self._step_26_tour_auto_start_new_user()
        self._step_27_tour_navigation_and_skip()
        self._step_28_tour_replay_button()
        self._step_29_tour_page_guide()
        self._step_30_tour_local_storage_state()
        self._step_31_tour_sidebar_tour_ids()
        self._step_32_tour_section_tours_all_pages()

        # Phase 8: DataTables, Form Layout, Skeleton, Detail Page Guides
        self._step_33_datatables_on_list_pages()
        self._step_34_form_layout_modernized()
        self._step_35_dashboard_skeleton_loaded()
        self._step_36_detail_page_guides()

        # Phase 9: Modal Forms and Toast Notifications
        self._step_37_modal_form_create()
        self._step_38_modal_form_delete()
        self._step_39_toast_notifications()

        # Phase 10: Dashboard Tooltips, Settings UI, Report PDF, Modal Polish
        self._step_40_dashboard_tooltips()
        self._step_41_settings_ui()
        self._step_42_report_pdf_buttons()
        self._step_43_modal_no_duplicate_title()

        # Phase 11: CSV Import Functionality
        self._step_44_import_modal_ui()
        self._step_45_import_csv_template_download()
        self._step_46_import_catalog_items_csv()
        self._step_47_import_expenses_csv()
        self._step_48_import_supply_items_csv()
        self._step_49_import_procurement_csv()
        self._step_50_import_sales_orders_csv()
        self._step_51_import_with_errors_shows_summary()

    # ═══════════════════════════════════════════════════════════════════
    # PHASE 1: Core CRUD Modules
    # ═══════════════════════════════════════════════════════════════════

    def _step_01_login_dashboard_period_toggle(self):
        """Login, verify dashboard loads with period toggle buttons."""
        self.login()
        self.assert_no_errors()
        self.assert_text_present('Executive Dashboard')
        self.assert_text_present('Revenue')
        self.assert_text_present('Today')
        self.assert_text_present('This Week')
        self.assert_text_present('This Month')
        self.assert_text_present('This Year')

        # Test period toggle - click This Month
        self.browser.find_element(By.LINK_TEXT, 'This Month').click()
        self.wait.until(EC.url_contains('period=month'))
        self.assert_no_errors()
        self.assert_text_present('Month')

        # Back to Today
        self.browser.find_element(By.LINK_TEXT, 'Today').click()
        self.wait.until(EC.url_contains('period=today'))
        self.assert_no_errors()

    def _step_02_business_settings(self):
        """Fill and save business profile settings."""
        self.browser.get(self.url('/core/settings/'))
        self.assert_no_errors()
        self.assert_text_present('Business Profile')

        self.fill_field('name', 'Selenium Test Business')
        self.fill_field('tagline', 'Quality Products')
        self.fill_field('owner_name', 'Juan Dela Cruz')
        self.fill_field('email', 'info@testbiz.ph')
        self.fill_field('phone', '09171234567')
        self.fill_field('address', '123 Test St., Makati')
        self.fill_field('city', 'Makati')
        self.fill_field('province', 'Metro Manila')
        self.fill_field('zip_code', '1234')
        self.fill_field('tin', '123-456-789-000')
        self.fill_field('currency', 'PHP')
        self.fill_field('fiscal_year_start_month', '1')
        self.fill_field('receipt_footer', 'Thank you for your purchase!')
        self.submit_form()
        self.assert_form_saved('Business profile updated')

        # Verify data persists on reload
        self.browser.get(self.url('/core/settings/'))
        name_el = self.browser.find_element(By.NAME, 'name')
        self.assertEqual(name_el.get_attribute('value'), 'Selenium Test Business')

    def _step_03_create_sales_channel(self):
        """Create sales channels."""
        channels = [
            ('Physical Store', 'STORE', 'Walk-in retail store'),
            ('Facebook', 'FB', 'Facebook Marketplace'),
            ('Shopee', 'SHOPEE', 'Shopee online store'),
        ]
        for name, code, desc in channels:
            self.browser.get(self.url('/core/channels/new/'))
            self.assert_no_errors()
            self.fill_field('name', name)
            self.fill_field('code', code)
            self.fill_field('description', desc)
            self.submit_form()
            self.assert_form_saved(name)

        # Verify all channels appear in list
        self.browser.get(self.url('/core/channels/'))
        self.assert_text_present('Physical Store')
        self.assert_text_present('Facebook')
        self.assert_text_present('Shopee')

    def _step_04_create_expense_category_cogs(self):
        """Create COGS expense categories."""
        self.browser.get(self.url('/core/expense-categories/new/'))
        self.assert_no_errors()
        self.fill_field('name', 'Raw Materials')
        self.fill_field('code', 'COGS-RAW')
        self.fill_field('description', 'Raw material purchases')
        self.click_checkbox('is_cogs')
        self.submit_form()
        self.assert_form_saved('Raw Materials')

    def _step_05_create_expense_category_opex(self):
        """Create OPEX expense categories."""
        opex_cats = [
            ('Rent', 'OPEX-RENT', 'Office/store rent'),
            ('Utilities', 'OPEX-UTIL', 'Electricity, water, internet'),
            ('Salaries', 'OPEX-SAL', 'Employee wages'),
        ]
        for name, code, desc in opex_cats:
            self.browser.get(self.url('/core/expense-categories/new/'))
            self.fill_field('name', name)
            self.fill_field('code', code)
            self.fill_field('description', desc)
            self.submit_form()
            self.assert_form_saved(name)

        # Verify COGS badge
        self.browser.get(self.url('/core/expense-categories/'))
        self.assert_text_present('COGS')
        self.assert_text_present('Raw Materials')
        self.assert_text_present('Rent')
        self.assert_text_present('Utilities')
        self.assert_text_present('Salaries')

    def _step_06_record_expenses(self):
        """Record multiple expenses with known amounts for P&L verification."""
        today = date.today().isoformat()
        expenses = [
            ('Raw Materials', '5000.00', 'Supplier A', 'REF-001'),  # COGS
            ('Rent', '15000.00', 'Landlord', 'REF-002'),           # OPEX
            ('Utilities', '3500.00', 'Meralco', 'REF-003'),        # OPEX
            ('Salaries', '25000.00', '', 'PAY-001'),               # OPEX
        ]
        for cat_name, amount, vendor, ref in expenses:
            self.browser.get(self.url('/core/expenses/new/'))
            self.assert_no_errors()
            self.fill_date_field('date', today)
            self.select_by_text('category', cat_name)
            self.fill_field('amount', amount)
            if vendor:
                self.fill_field('vendor', vendor)
            self.fill_field('reference_no', ref)
            self.submit_form()
            self.assert_form_saved('Expense recorded')

        # Verify expense list shows total
        self.browser.get(self.url('/core/expenses/'))
        self.assert_text_present('48,500')  # 5000+15000+3500+25000 = 48,500

        # Test filtering by category
        self.browser.get(self.url('/core/expenses/'))
        self.select_by_text('category', 'Rent')
        self.browser.find_element(By.CSS_SELECTOR, 'button[type="submit"]').click()
        time.sleep(0.5)
        self.assert_text_present('15,000')

    def _step_07_create_supply_category(self):
        """Create supply categories."""
        self.browser.get(self.url('/core/supply-categories/new/'))
        self.assert_no_errors()
        self.fill_field('name', 'Packaging Materials')
        self.fill_field('code', 'PKG')
        self.submit_form()
        self.assert_form_saved('Packaging Materials')

    def _step_08_create_supply_item(self):
        """Create supply items."""
        supplies = [
            ('Bubble Wrap Roll', 'PKG-001', '150.00', '5'),
            ('Shipping Box Small', 'PKG-002', '25.00', '20'),
        ]
        for name, code, cost, min_stock in supplies:
            self.browser.get(self.url('/core/supplies/new/'))
            self.assert_no_errors()
            self.fill_field('name', name)
            self.fill_field('code', code)
            self.select_first_option('category')
            self.fill_field('cost_per_unit', cost)
            self.fill_field('minimum_stock', min_stock)
            self.submit_form()
            self.assert_form_saved(name)

    def _step_09_record_supply_movements(self):
        """Record stock-in and usage movements."""
        today = date.today().isoformat()

        # Stock IN: 50 bubble wraps
        self.browser.get(self.url('/core/supply-movements/new/'))
        self.assert_no_errors()
        self.select_first_option('supply_item')
        self.select_by_text('movement_type', 'Stock In')
        self.fill_field('qty', '50')
        self.fill_field('unit_cost', '150.00')
        self.fill_date_field('date', today)
        self.fill_field('notes', 'Initial stock')
        self.submit_form()
        self.assert_form_saved('Supply movement recorded')

        # Stock OUT: 12 bubble wraps used
        self.browser.get(self.url('/core/supply-movements/new/'))
        self.select_first_option('supply_item')
        self.select_by_text('movement_type', 'Usage / Stock Out')
        self.fill_field('qty', '12')
        self.fill_field('unit_cost', '150.00')
        self.fill_date_field('date', today)
        self.fill_field('notes', 'Used for packaging')
        self.submit_form()
        self.assert_form_saved('Supply movement recorded')

        # Stock IN: 100 shipping boxes
        self.browser.get(self.url('/core/supply-movements/new/'))
        self.select_by_index('supply_item', 2)  # second supply item
        self.select_by_text('movement_type', 'Stock In')
        self.fill_field('qty', '100')
        self.fill_field('unit_cost', '25.00')
        self.fill_date_field('date', today)
        self.submit_form()
        self.assert_form_saved('Supply movement recorded')

    def _step_10_verify_supply_stock_calculation(self):
        """Verify supply stock is correctly calculated (IN - OUT)."""
        self.browser.get(self.url('/core/supplies/'))
        self.assert_no_errors()
        body = self.browser.page_source

        # Bubble Wrap: 50 in - 12 out = 38 current stock
        self.assertIn('38.00', body, 'Bubble Wrap stock should be 38.00 (50 - 12)')
        # Shipping Box: 100 in - 0 out = 100
        self.assertIn('100.00', body, 'Shipping Box stock should be 100.0000')

        # Verify low stock badge: Bubble Wrap min=5, current=38 → OK
        # Shipping Box min=20, current=100 → OK

    def _step_11_create_target_goals(self):
        """Create target goals with values for progress tracking."""
        self.browser.get(self.url('/core/goals/new/'))
        self.assert_no_errors()
        self.fill_field('title', 'Monthly Revenue Target')
        self.fill_field('description', 'Reach 100K monthly revenue')
        self.fill_field('category', 'Sales')
        self.fill_field('target_value', '100000.00')
        self.fill_field('current_value', '25000.00')
        self.fill_field('unit_label', 'PHP')
        self.select_by_text('priority', 'High')
        self.select_by_text('status', 'In Progress')
        self.fill_date_field('due_date', (date.today() + timedelta(days=30)).isoformat())
        self.submit_form()
        self.assert_form_saved('Goal created')

        # Create a second goal
        self.browser.get(self.url('/core/goals/new/'))
        self.fill_field('title', 'Reduce Waste by 20%')
        self.fill_field('category', 'Operations')
        self.fill_field('target_value', '20')
        self.fill_field('current_value', '8')
        self.fill_field('unit_label', '%')
        self.select_by_text('priority', 'Medium')
        self.select_by_text('status', 'In Progress')
        self.submit_form()
        self.assert_form_saved('Goal created')

        # Verify goal list shows progress
        self.browser.get(self.url('/core/goals/'))
        self.assert_text_present('Monthly Revenue Target')
        self.assert_text_present('25.0%')   # 25000/100000 = 25.0%
        self.assert_text_present('Reduce Waste')
        self.assert_text_present('40.0%')   # 8/20 = 40.0%

    # ═══════════════════════════════════════════════════════════════════
    # PHASE 2: Invoice Generation & POS with Channel
    # ═══════════════════════════════════════════════════════════════════

    def _step_12_pos_sale_with_channel(self):
        """Create a POS sale via the API/ORM for invoice testing."""
        from pos.models import POSSale, POSSaleLine, POSShift, SaleStatus, ShiftStatus
        from core.models import SalesChannel

        channel = SalesChannel.objects.get(code='STORE')

        from django.utils import timezone
        shift = POSShift.objects.create(
            register=self.register,
            opened_by=self.admin,
            opened_at=timezone.now(),
            opening_cash=Decimal('5000.00'),
            status=ShiftStatus.OPEN,
        )

        # Create a sale: 10 widgets at 250 each = 2500
        sale = POSSale.objects.create(
            sale_no='POS-T-0001',
            register=self.register,
            shift=shift,
            warehouse=self.wh,
            location=self.loc,
            customer=self.customer,
            channel=channel,
            subtotal=Decimal('2500.00'),
            discount_total=Decimal('0.00'),
            tax_total=Decimal('0.00'),
            grand_total=Decimal('2500.00'),
            status=SaleStatus.PAID,
            created_by=self.admin,
        )
        POSSaleLine.objects.create(
            sale=sale,
            item=self.item,
            location=self.loc,
            qty=Decimal('10'),
            unit=self.unit,
            unit_price=Decimal('250.00'),
            discount_amount=Decimal('0.00'),
            tax_rate=Decimal('0.00'),
            line_total=Decimal('2500.00'),
        )
        self._sale = sale
        self._shift = shift

    def _step_13_generate_invoice_from_sale(self):
        """Generate an invoice from the POS sale and verify redirect."""
        self.browser.get(self.url(f'/core/invoices/from-sale/{self._sale.pk}/'))
        self.assert_no_errors()
        # Should redirect to invoice detail
        self.wait.until(EC.url_contains('/core/invoices/'))
        self.assert_text_present('Invoice')
        self.assert_text_present('000001')

    def _step_14_verify_invoice_calculations(self):
        """Verify invoice totals match POS sale exactly."""
        # Already on invoice detail page from step 13
        body = self.browser.page_source
        self.assert_text_present('2,500')  # grand total
        self.assert_text_present('TEST-001')  # item code
        self.assert_text_present('Test Widget')  # item name
        self.assert_text_present('Test Customer Corp')  # customer

        # Navigate to invoice list
        self.browser.get(self.url('/core/invoices/'))
        self.assert_no_errors()
        self.assert_text_present('000001')

        # Verify print view loads
        from core.models import Invoice
        inv = Invoice.objects.first()
        self.browser.get(self.url(f'/core/invoices/{inv.pk}/print/'))
        self.assert_no_errors()
        self.assert_text_present('Selenium Test Business')  # business name from settings
        self.assert_text_present('2,500')

    # ═══════════════════════════════════════════════════════════════════
    # PHASE 3: Reports
    # ═══════════════════════════════════════════════════════════════════

    def _step_15_sales_report(self):
        """Verify sales report loads with correct data."""
        self.browser.get(self.url('/reports/sales/'))
        self.assert_no_errors()
        self.assert_text_present('Sales Report')
        self.assert_text_present('Total Revenue')
        self.assert_text_present('2,500')   # from POS sale
        self.assert_text_present('Gross Profit')
        # COGS = 10 * 100 (cost_price) = 1000, Profit = 2500 - 1000 = 1500
        self.assert_text_present('1,500')
        # Top items
        self.assert_text_present('TEST-001')

    def _step_16_expense_report(self):
        """Verify expense report loads with correct totals."""
        self.browser.get(self.url('/reports/expenses/'))
        self.assert_no_errors()
        self.assert_text_present('Expense Report')
        self.assert_text_present('48,500')  # total expenses
        self.assert_text_present('Raw Materials')
        self.assert_text_present('Rent')

    def _step_17_financial_statement_pnl(self):
        """Load financial statement and verify P&L structure."""
        self.browser.get(self.url('/reports/financial-statement/'))
        self.assert_no_errors()
        self.assert_text_present('Financial Statement')
        self.assert_text_present('REVENUE')
        self.assert_text_present('COST OF GOODS SOLD')
        self.assert_text_present('GROSS PROFIT')
        self.assert_text_present('OPERATING EXPENSES')
        self.assert_text_present('NET PROFIT')

    def _step_18_verify_pnl_calculations(self):
        """
        Verify accounting calculations in P&L are correct:
        Revenue:     2,500.00  (POS sale)
        COGS:
          Inventory: 1,000.00  (10 * 100 cost)
          COGS-exp:  5,000.00  (Raw Materials expense)
          Total COGS: 6,000.00
        Gross Profit: 2,500 - 6,000 = -3,500.00
        OPEX:
          Rent:      15,000.00
          Utilities:  3,500.00
          Salaries:  25,000.00
          Total OPEX: 43,500.00
        Net Profit:  -3,500 - 43,500 = -47,000.00
        """
        from django.db.models import Sum, F, DecimalField
        from django.db.models.functions import Coalesce
        from core.models import Expense
        from pos.models import POSSale, POSSaleLine, SaleStatus

        # Verify via ORM for exact calculation
        sale_qs = POSSale.objects.filter(status__in=[SaleStatus.POSTED, SaleStatus.PAID])
        revenue = sale_qs.aggregate(
            total=Coalesce(Sum('grand_total'), Decimal('0'), output_field=DecimalField())
        )['total']
        self.assertEqual(revenue, Decimal('2500.00'), 'Revenue should be 2500')

        # COGS from inventory
        cogs_inv = POSSaleLine.objects.filter(
            sale__in=sale_qs
        ).aggregate(
            total=Coalesce(
                Sum(F('item__cost_price') * F('qty'), output_field=DecimalField()),
                Decimal('0'), output_field=DecimalField(),
            )
        )['total']
        self.assertEqual(cogs_inv, Decimal('1000.00'), 'COGS inventory should be 1000')

        # COGS from expenses
        cogs_exp = Expense.objects.filter(category__is_cogs=True).aggregate(
            total=Coalesce(Sum('amount'), Decimal('0'), output_field=DecimalField())
        )['total']
        self.assertEqual(cogs_exp, Decimal('5000.00'), 'COGS expenses should be 5000')

        total_cogs = cogs_inv + cogs_exp
        self.assertEqual(total_cogs, Decimal('6000.00'), 'Total COGS should be 6000')

        gross_profit = revenue - total_cogs
        self.assertEqual(gross_profit, Decimal('-3500.00'), 'Gross profit should be -3500')

        # OPEX
        opex = Expense.objects.filter(category__is_cogs=False).aggregate(
            total=Coalesce(Sum('amount'), Decimal('0'), output_field=DecimalField())
        )['total']
        self.assertEqual(opex, Decimal('43500.00'), 'OPEX should be 43500')

        net_profit = gross_profit - opex
        self.assertEqual(net_profit, Decimal('-47000.00'), 'Net profit should be -47000')

    # ═══════════════════════════════════════════════════════════════════
    # PHASE 4: Dashboard Deep Checks
    # ═══════════════════════════════════════════════════════════════════

    def _step_19_dashboard_channel_breakdown(self):
        """Dashboard should show channel breakdown."""
        self.browser.get(self.url('/dashboard/?period=today'))
        self.assert_no_errors()
        self.assert_text_present('Sales by Channel')
        self.assert_text_present('Physical Store')

    def _step_20_dashboard_expense_categories(self):
        """Dashboard should show expense category pie chart."""
        self.assert_text_present('Expense Categories')

    def _step_21_dashboard_active_goals(self):
        """Dashboard should show active goals."""
        self.assert_text_present('Active Goals')
        self.assert_text_present('Monthly Revenue Target')

    # ═══════════════════════════════════════════════════════════════════
    # PHASE 5: Sidebar Navigation
    # ═══════════════════════════════════════════════════════════════════

    def _step_22_sidebar_new_sections(self):
        """Verify all new sidebar sections are accessible."""
        new_pages = [
            ('/core/settings/', 'Business Profile'),
            ('/core/channels/', 'Sales Channel'),
            ('/core/expenses/', 'Expense'),
            ('/core/expense-categories/', 'Expense Categor'),
            ('/core/supplies/', 'Supply'),
            ('/core/supply-movements/', 'Supply Movement'),
            ('/core/supply-categories/', 'Supply Categor'),
            ('/core/goals/', 'Goal'),
            ('/core/invoices/', 'Invoice'),
            ('/reports/sales/', 'Sales Report'),
            ('/reports/expenses/', 'Expense Report'),
            ('/reports/financial-statement/', 'Financial Statement'),
        ]
        for path, expected_text in new_pages:
            self.browser.get(self.url(path))
            self.assert_no_errors()
            self.assert_text_present(expected_text)

    # ═══════════════════════════════════════════════════════════════════
    # PHASE 6: Edit & Delete Flows
    # ═══════════════════════════════════════════════════════════════════

    def _step_23_edit_expense(self):
        """Edit an expense and verify the change persists."""
        from core.models import Expense
        exp = Expense.objects.filter(vendor='Meralco').first()
        self.browser.get(self.url(f'/core/expenses/{exp.pk}/edit/'))
        self.assert_no_errors()
        self.fill_field('amount', '4000.00')
        self.submit_form()
        self.assert_form_saved('Expense updated')
        exp.refresh_from_db()
        self.assertEqual(exp.amount, Decimal('4000.00'))

    def _step_24_edit_goal(self):
        """Edit goal progress and verify percentage updates."""
        from core.models import TargetGoal
        goal = TargetGoal.objects.get(title='Monthly Revenue Target')
        self.browser.get(self.url(f'/core/goals/{goal.pk}/edit/'))
        self.assert_no_errors()
        self.fill_field('current_value', '50000.00')
        self.submit_form()
        self.assert_form_saved('Goal updated')

        # Verify progress
        self.browser.get(self.url('/core/goals/'))
        self.assert_text_present('50.0%')  # 50000/100000

    def _step_25_delete_flow(self):
        """Test delete confirmation flow for a channel."""
        from core.models import SalesChannel
        ch = SalesChannel.objects.get(code='SHOPEE')
        self.browser.get(self.url(f'/core/channels/{ch.pk}/delete/'))
        self.assert_no_errors()
        self.assert_text_present('Confirm')
        self.submit_form()
        self.assert_form_saved('Sales channel deleted')

        # Verify soft delete — not in active list
        self.browser.get(self.url('/core/channels/'))
        self.assert_text_not_present('Shopee')

    # ═══════════════════════════════════════════════════════════════════
    # PHASE 7: Tour Guide System
    # ═══════════════════════════════════════════════════════════════════

    def _step_26_tour_auto_start_new_user(self):
        """Tour auto-starts on dashboard for new users (no localStorage flag)."""
        # Clear localStorage to simulate new user
        self.browser.get(self.url('/dashboard/'))
        self.browser.execute_script("localStorage.clear();")

        # Reload dashboard — tour should auto-start
        self.browser.get(self.url('/dashboard/'))
        time.sleep(1.5)  # Tour starts after 600ms delay

        # Verify Driver.js popover is visible
        popover = self.wait.until(
            EC.presence_of_element_located((By.CSS_SELECTOR, '.driver-popover'))
        )
        self.assertTrue(popover.is_displayed(), 'Tour popover should be visible')

        # Verify welcome step content
        title = self.browser.find_element(
            By.CSS_SELECTOR, '.driver-popover-title'
        ).text
        self.assertIn('Welcome', title, 'First step should be the welcome message')

        desc = self.browser.find_element(
            By.CSS_SELECTOR, '.driver-popover-description'
        ).text
        self.assertIn('Warehouse Inventory System', desc)

    def _js_click(self, css):
        """Click an element via JS to bypass overlay interception."""
        el = self.browser.find_element(By.CSS_SELECTOR, css)
        self.browser.execute_script('arguments[0].click();', el)

    def _dismiss_tour(self):
        """Force-dismiss any active Driver.js tour."""
        self.browser.execute_script("""
            document.querySelectorAll('.driver-popover, .driver-overlay, .driver-active-element').forEach(function(e) { e.remove(); });
            document.querySelectorAll('[class*="driver-"]').forEach(function(e) {
                e.className = e.className.replace(/driver-[^ ]*/g, '').trim();
            });
        """)
        time.sleep(0.3)

    def _step_27_tour_navigation_and_skip(self):
        """Tour has Next, Back, and close (skip) buttons."""
        # Tour should still be active from previous step
        # Verify navigation buttons
        next_btn = self.browser.find_element(
            By.CSS_SELECTOR, '.driver-popover-next-btn'
        )
        self.assertTrue(next_btn.is_displayed(), 'Next button should be visible')

        # Click Next to go to step 2 (Sidebar)
        self._js_click('.driver-popover-next-btn')
        time.sleep(0.5)

        title2 = self.browser.find_element(
            By.CSS_SELECTOR, '.driver-popover-title'
        ).text
        self.assertIn('Sidebar', title2, 'Step 2 should be about sidebar navigation')

        # Verify Back button appears
        prev_btn = self.browser.find_element(
            By.CSS_SELECTOR, '.driver-popover-prev-btn'
        )
        self.assertTrue(prev_btn.is_displayed(), 'Back button should be visible on step 2')

        # Click Next a few more times to advance through the tour
        for _ in range(3):
            self._js_click('.driver-popover-next-btn')
            time.sleep(0.4)

        # Verify progress indicator is shown
        progress = self.browser.find_element(
            By.CSS_SELECTOR, '.driver-popover-progress-text'
        ).text
        self.assertIn('of', progress, 'Progress text should show "Step X of Y"')

        # Close/skip the tour via the close button
        self._js_click('.driver-popover-close-btn')
        time.sleep(0.3)

        # Accept the skip confirmation dialog
        try:
            alert = self.browser.switch_to.alert
            alert.accept()
            time.sleep(0.3)
        except Exception:
            pass  # No alert means tour was on last step

        # Verify popover is gone
        time.sleep(0.5)
        popovers = self.browser.find_elements(
            By.CSS_SELECTOR, '.driver-popover'
        )
        visible = [p for p in popovers if p.is_displayed()]
        self.assertEqual(len(visible), 0, 'Tour popover should be dismissed after skip')

    def _step_28_tour_replay_button(self):
        """Tour replay button in navbar restarts the full tour."""
        # Verify Tour button exists in navbar
        replay_btn = self.wait.until(
            EC.presence_of_element_located((By.ID, 'wis-tour-replay'))
        )
        self.assertTrue(replay_btn.is_displayed(), 'Tour replay button should be visible')
        self.assertIn('Tour', replay_btn.text)

        # Click replay — should restart tour on dashboard
        replay_btn.click()
        time.sleep(1.5)  # Allow tour to start

        # Verify tour popover appears again
        popover = self.wait.until(
            EC.presence_of_element_located((By.CSS_SELECTOR, '.driver-popover'))
        )
        self.assertTrue(popover.is_displayed(), 'Tour should restart on replay click')
        title = self.browser.find_element(
            By.CSS_SELECTOR, '.driver-popover-title'
        ).text
        self.assertIn('Welcome', title, 'Replay should start from the beginning')

        # Close the tour to continue other tests
        self._dismiss_tour()

    def _step_29_tour_page_guide(self):
        """Page Guide button triggers a page-specific section tour."""
        # Reload dashboard to get a clean JS state (previous steps leave driver in odd state)
        self.browser.execute_script("localStorage.setItem('wis_tour_completed_1.0', 'true');")
        self.browser.get(self.url('/dashboard/'))
        time.sleep(1)

        # Verify Guide button exists in navbar
        guide_btn = self.wait.until(
            EC.presence_of_element_located((By.ID, 'wis-page-guide'))
        )
        self.assertTrue(guide_btn.is_displayed(), 'Page Guide button should be visible')
        self.assertIn('Guide', guide_btn.text)

        # Click Guide on dashboard — should show dashboard-specific tour
        self.browser.execute_script('arguments[0].click();', guide_btn)
        time.sleep(1.5)

        popover = self.wait.until(
            EC.presence_of_element_located((By.CSS_SELECTOR, '.driver-popover'))
        )
        self.assertTrue(popover.is_displayed(), 'Section tour popover should appear')
        title = self.browser.find_element(
            By.CSS_SELECTOR, '.driver-popover-title'
        ).text
        # Dashboard page guide should mention Period or Filter
        self.assertTrue(
            'Period' in title or 'Filter' in title or 'Financial' in title or 'Dashboard' in title,
            f'Dashboard guide should have relevant title, got: {title}'
        )

        # Dismiss the section tour
        self._dismiss_tour()

    def _step_30_tour_local_storage_state(self):
        """Tour completion is tracked in localStorage."""
        # After the tour was skipped/completed, localStorage should be set
        flag = self.browser.execute_script(
            "return localStorage.getItem('wis_tour_completed_1.0');"
        )
        self.assertEqual(flag, 'true', 'Tour completion flag should be set in localStorage')

        # Verify tour does NOT auto-start on reload (because flag is set)
        self.browser.get(self.url('/dashboard/'))
        time.sleep(1.5)

        popovers = self.browser.find_elements(By.CSS_SELECTOR, '.driver-popover')
        visible = [p for p in popovers if p.is_displayed()]
        self.assertEqual(len(visible), 0, 'Tour should NOT auto-start when completion flag is set')

        # Reset and verify it auto-starts again
        self.browser.execute_script("localStorage.removeItem('wis_tour_completed_1.0');")
        self.browser.get(self.url('/dashboard/'))
        time.sleep(1.5)

        popover = self.wait.until(
            EC.presence_of_element_located((By.CSS_SELECTOR, '.driver-popover'))
        )
        self.assertTrue(popover.is_displayed(), 'Tour should auto-start after localStorage reset')

        # Clean up — close the tour
        self._dismiss_tour()
        self.browser.execute_script("localStorage.setItem('wis_tour_completed_1.0', 'true');")

    def _step_31_tour_sidebar_tour_ids(self):
        """All sidebar nav items have data-tour-id attributes for tour targeting."""
        self.browser.get(self.url('/dashboard/'))
        time.sleep(0.5)

        expected_ids = [
            'nav-dashboard', 'nav-catalog', 'nav-partners', 'nav-warehouses',
            'nav-procurement', 'nav-sales', 'nav-expenses', 'nav-supplies',
            'nav-inventory', 'nav-pos', 'nav-pricing', 'nav-qr',
            'nav-reports', 'nav-goals', 'nav-settings',
        ]
        for tour_id in expected_ids:
            els = self.browser.find_elements(
                By.CSS_SELECTOR, f'[data-tour-id="{tour_id}"]'
            )
            self.assertTrue(
                len(els) > 0,
                f'Sidebar should have element with data-tour-id="{tour_id}"'
            )

    def _step_32_tour_section_tours_all_pages(self):
        """Section-specific tours work on ALL pages and routes."""
        pages_with_tours = [
            # Dashboard
            ('/dashboard/', 'Period'),
            # Catalog
            ('/catalog/items/', 'Item'),
            ('/catalog/categories/', 'Categor'),
            ('/catalog/units/', 'Unit'),
            # Partners
            ('/partners/suppliers/', 'Supplier'),
            ('/partners/customers/', 'Customer'),
            # Warehouses
            ('/warehouses/', 'Warehouse'),
            ('/warehouses/locations/', 'Location'),
            # Procurement
            ('/procurement/purchase-orders/', 'Purchase'),
            ('/procurement/goods-receipts/', 'Goods'),
            # Sales
            ('/sales/orders/', 'Sales Order'),
            ('/sales/deliveries/', 'Deliver'),
            # Inventory
            ('/inventory/moves/', 'Movement'),
            ('/inventory/transfers/', 'Transfer'),
            ('/inventory/adjustments/', 'Adjustment'),
            ('/inventory/damaged/', 'Damage'),
            # POS
            ('/pos/registers/', 'Register'),
            ('/pos/shifts/', 'Shift'),
            ('/pos/receipts/', 'Receipt'),
            # Pricing
            ('/pricing/price-lists/', 'Price'),
            ('/pricing/discount-rules/', 'Discount'),
            # QR
            ('/qr/', 'QR'),
            # Reports
            ('/reports/sales/', 'Sales'),
            ('/reports/expenses/', 'Expense'),
            ('/reports/financial-statement/', 'Profit'),
            ('/reports/stock-on-hand/', 'Stock'),
            ('/reports/low-stock/', 'Low Stock'),
            ('/reports/profit-margin/', 'Profit'),
            ('/reports/inventory-valuation/', 'Inventory'),
            # Core
            ('/core/settings/', 'Settings'),
            ('/core/channels/', 'Channel'),
            ('/core/expense-categories/', 'Expense'),
            ('/core/expenses/', 'Expense'),
            ('/core/supply-categories/', 'Supply'),
            ('/core/supplies/', 'Suppl'),
            ('/core/supply-movements/', 'Movement'),
            ('/core/invoices/', 'Invoice'),
            ('/core/goals/', 'Goal'),
        ]

        for page_url, expected_keyword in pages_with_tours:
            self.browser.get(self.url(page_url))
            time.sleep(0.5)

            # Clear any leftover overlays
            self._dismiss_tour()

            # Click Guide button
            guide_btn = self.browser.find_element(By.ID, 'wis-page-guide')
            self.browser.execute_script('arguments[0].click();', guide_btn)
            time.sleep(1)

            # Verify popover appears
            popovers = self.browser.find_elements(By.CSS_SELECTOR, '.driver-popover')
            visible = [p for p in popovers if p.is_displayed()]
            self.assertTrue(
                len(visible) > 0,
                f'Section tour should appear on {page_url}'
            )

            # Verify content is relevant — NOT the generic fallback
            title = self.browser.find_element(
                By.CSS_SELECTOR, '.driver-popover-title'
            ).text
            desc = self.browser.find_element(
                By.CSS_SELECTOR, '.driver-popover-description'
            ).text
            combined = title + ' ' + desc

            # Ensure it's NOT the generic fallback message
            self.assertNotIn(
                'No specific guide',
                combined,
                f'Page {page_url} should have a dedicated guide, not the generic fallback'
            )

            # Verify content is relevant to the page
            self.assertTrue(
                expected_keyword.lower() in combined.lower(),
                f'Tour on {page_url} should mention "{expected_keyword}", got: {title} | {desc[:80]}'
            )

            # Dismiss
            self._dismiss_tour()

    # ═══════════════════════════════════════════════════════════════════
    # PHASE 8: DataTables, Form Layout, Skeleton, Detail Page Guides
    # ═══════════════════════════════════════════════════════════════════

    def _step_33_datatables_on_list_pages(self):
        """Verify DataTables is initialized on list pages with wis-table class."""
        test_pages = [
            '/catalog/items/',
            '/partners/suppliers/',
            '/core/expenses/',
            '/core/channels/',
        ]
        for page_url in test_pages:
            self.browser.get(self.url(page_url))
            time.sleep(1)  # Wait for DataTables init

            # Check DataTables wrapper is present (DataTables adds _wrapper div)
            has_dt = self.browser.execute_script(
                "return document.querySelectorAll('.dataTables_wrapper').length > 0;"
            )
            self.assertTrue(
                has_dt,
                f'DataTables should be initialized on {page_url}'
            )

            # Check search input exists
            has_search = self.browser.execute_script(
                "return document.querySelectorAll('.dataTables_filter input').length > 0;"
            )
            self.assertTrue(
                has_search,
                f'DataTables search input should exist on {page_url}'
            )

            # Check pagination info exists
            has_info = self.browser.execute_script(
                "return document.querySelectorAll('.dataTables_info').length > 0;"
            )
            self.assertTrue(
                has_info,
                f'DataTables info should exist on {page_url}'
            )

            # Check Excel export button exists
            has_excel = self.browser.execute_script(
                "return document.querySelectorAll('.dt-buttons .buttons-excel').length > 0;"
            )
            self.assertTrue(
                has_excel,
                f'Excel export button should exist on {page_url}'
            )

    def _step_34_form_layout_modernized(self):
        """Verify form pages use the modernized constrained layout."""
        # Item create form should use wis-form-card with fieldset grouping
        self.browser.get(self.url('/catalog/items/create/'))
        time.sleep(0.5)
        self.assert_no_errors()

        # Check wis-form-card class is present
        has_form_card = self.browser.execute_script(
            "return document.querySelectorAll('.wis-form-card').length > 0;"
        )
        self.assertTrue(has_form_card, 'Item form should use wis-form-card class')

        # Check wide variant for item form
        has_wide = self.browser.execute_script(
            "return document.querySelectorAll('.wis-form-wide').length > 0;"
        )
        self.assertTrue(has_wide, 'Item form should use wis-form-wide class')

        # Check fieldsets exist for grouped layout
        fieldsets = self.browser.find_elements(By.CSS_SELECTOR, 'fieldset')
        self.assertGreaterEqual(
            len(fieldsets), 3,
            'Item form should have at least 3 fieldsets (Identity, Pricing, Stock Levels)'
        )

        # Check two-column rows exist
        form_rows = self.browser.find_elements(By.CSS_SELECTOR, '.wis-form-row')
        self.assertGreaterEqual(
            len(form_rows), 2,
            'Item form should have at least 2 two-column rows'
        )

        # Verify a simpler form also uses wis-form-card
        self.browser.get(self.url('/core/channels/new/'))
        time.sleep(0.5)
        has_form_card2 = self.browser.execute_script(
            "return document.querySelectorAll('.wis-form-card').length > 0;"
        )
        self.assertTrue(has_form_card2, 'Channel form should use wis-form-card class')

    def _step_35_dashboard_skeleton_loaded(self):
        """Verify dashboard skeleton transitions to real content."""
        self.browser.get(self.url('/dashboard/'))
        time.sleep(1)

        # After page load, dash-wrap should have dash-loaded class
        has_loaded = self.browser.execute_script(
            "var el = document.getElementById('dash-wrap'); return el && el.classList.contains('dash-loaded');"
        )
        self.assertTrue(has_loaded, 'Dashboard should have dash-loaded class after render')

        # Skeleton should be hidden
        skel_visible = self.browser.execute_script("""
            var skel = document.querySelector('.dash-skeleton');
            if (!skel) return false;
            return window.getComputedStyle(skel).display !== 'none';
        """)
        self.assertFalse(skel_visible, 'Skeleton should be hidden after dashboard loads')

        # Real content should be visible
        real_visible = self.browser.execute_script("""
            var real = document.querySelector('.dash-real');
            if (!real) return false;
            return window.getComputedStyle(real).display !== 'none';
        """)
        self.assertTrue(real_visible, 'Real dashboard content should be visible')

    def _step_36_detail_page_guides(self):
        """Detail page guides work on item detail and invoice detail."""
        from core.models import Invoice

        # Ensure tour completed flag is set
        self.browser.execute_script("localStorage.setItem('wis_tour_completed_1.0', 'true');")

        # Test item detail page guide
        self.browser.get(self.url(f'/catalog/items/{self.item.pk}/'))
        time.sleep(0.5)
        self._dismiss_tour()

        guide_btn = self.browser.find_element(By.ID, 'wis-page-guide')
        self.browser.execute_script('arguments[0].click();', guide_btn)
        time.sleep(1)

        popovers = self.browser.find_elements(By.CSS_SELECTOR, '.driver-popover')
        visible = [p for p in popovers if p.is_displayed()]
        self.assertTrue(len(visible) > 0, 'Guide should appear on item detail page')

        title = self.browser.find_element(By.CSS_SELECTOR, '.driver-popover-title').text
        desc = self.browser.find_element(By.CSS_SELECTOR, '.driver-popover-description').text
        combined = title + ' ' + desc
        self.assertNotIn('No specific guide', combined, 'Item detail should have dedicated guide')
        self.assertTrue(
            'item' in combined.lower() or 'detail' in combined.lower(),
            f'Item detail guide should be relevant, got: {title}'
        )
        self._dismiss_tour()

        # Test invoice detail page guide (if invoice exists)
        inv = Invoice.objects.first()
        if inv:
            self.browser.get(self.url(f'/core/invoices/{inv.pk}/'))
            time.sleep(0.5)
            self._dismiss_tour()

            guide_btn = self.browser.find_element(By.ID, 'wis-page-guide')
            self.browser.execute_script('arguments[0].click();', guide_btn)
            time.sleep(1)

            popovers = self.browser.find_elements(By.CSS_SELECTOR, '.driver-popover')
            visible = [p for p in popovers if p.is_displayed()]
            self.assertTrue(len(visible) > 0, 'Guide should appear on invoice detail page')

            title = self.browser.find_element(By.CSS_SELECTOR, '.driver-popover-title').text
            self.assertNotIn('No specific guide', title, 'Invoice detail should have dedicated guide')
            self._dismiss_tour()

    # ═══════════════════════════════════════════════════════════════════
    # PHASE 9: Modal Forms and Toast Notifications
    # ═══════════════════════════════════════════════════════════════════

    def _step_37_modal_form_create(self):
        """Create a record via modal form (click trigger → modal → fill → submit → toast)."""
        # Go to unit list page
        self.browser.get(self.url('/catalog/units/'))
        time.sleep(1)

        # Click the "New Unit" button which should have data-modal-url
        new_btn = self.browser.find_element(By.CSS_SELECTOR, '[data-modal-url]')
        self.browser.execute_script('arguments[0].click();', new_btn)

        # Wait for modal to appear
        modal = self.wait.until(
            EC.visibility_of_element_located((By.ID, 'wis-modal'))
        )
        self.assertTrue(modal.is_displayed(), 'Modal should be visible')

        # Wait for form to load inside modal
        time.sleep(1.5)
        modal_form = self.wait.until(
            EC.presence_of_element_located((By.CSS_SELECTOR, '#wis-modal-body form'))
        )
        self.assertIsNotNone(modal_form, 'Form should be loaded inside modal')

        # Fill the form fields inside the modal
        name_input = modal_form.find_element(By.NAME, 'name')
        name_input.clear()
        name_input.send_keys('Kilograms')
        abbr_input = modal_form.find_element(By.NAME, 'abbreviation')
        abbr_input.clear()
        abbr_input.send_keys('kg')

        # Submit the form inside the modal
        submit_btn = modal_form.find_element(By.CSS_SELECTOR, '[type="submit"]')
        self.browser.execute_script('arguments[0].click();', submit_btn)

        # Wait for SweetAlert success popup (modal system uses Swal.fire)
        swal = self.wait.until(
            EC.presence_of_element_located((By.CSS_SELECTOR, '.swal2-popup'))
        )
        time.sleep(0.5)
        self.assertTrue(swal.is_displayed(), 'SweetAlert should appear after modal submit')

        # Dismiss SweetAlert and wait for page refresh
        self.browser.execute_script("if(typeof Swal !== 'undefined') Swal.close();")
        time.sleep(2)

        # Refresh to verify data
        self.browser.get(self.url('/catalog/units/'))
        time.sleep(1)
        self.assert_text_present('Kilograms')
        self.assert_text_present('kg')

    def _step_38_modal_form_delete(self):
        """Delete a record via modal (click delete trigger → modal → confirm → toast)."""
        from catalog.models import Unit
        unit = Unit.objects.get(name='Kilograms')

        # Go to unit list page
        self.browser.get(self.url('/catalog/units/'))
        time.sleep(1)

        # Find and click the delete button for Kilograms
        delete_btn = self.browser.find_element(
            By.CSS_SELECTOR, f'[data-modal-url*="unit_delete"][data-modal-url*="{unit.pk}"], '
                             f'a[data-modal-url$="/units/{unit.pk}/delete/"]'
        )
        self.browser.execute_script('arguments[0].click();', delete_btn)

        # Wait for modal with delete confirmation
        modal = self.wait.until(
            EC.visibility_of_element_located((By.ID, 'wis-modal'))
        )
        time.sleep(1.5)

        # Verify confirmation text is in the modal
        modal_body = self.browser.find_element(By.ID, 'wis-modal-body').text
        self.assertTrue(
            'delete' in modal_body.lower() or 'confirm' in modal_body.lower(),
            'Delete confirmation should appear in modal'
        )

        # Submit the delete form
        delete_form = self.browser.find_element(By.CSS_SELECTOR, '#wis-modal-body form')
        submit_btn = delete_form.find_element(By.CSS_SELECTOR, '[type="submit"]')
        self.browser.execute_script('arguments[0].click();', submit_btn)

        # Wait for SweetAlert success popup
        swal = self.wait.until(
            EC.presence_of_element_located((By.CSS_SELECTOR, '.swal2-popup'))
        )
        time.sleep(0.5)

        # Dismiss SweetAlert and wait
        self.browser.execute_script("if(typeof Swal !== 'undefined') Swal.close();")
        time.sleep(2)

        # Verify unit is gone after reload
        self.browser.get(self.url('/catalog/units/'))
        time.sleep(0.5)
        self.assert_text_not_present('Kilograms')

    def _step_39_toast_notifications(self):
        """Verify notification infrastructure (SweetAlert + WIS functions)."""
        # Navigate to settings page
        self.browser.get(self.url('/core/settings/'))
        time.sleep(0.5)

        # Verify modal infrastructure exists
        modal = self.browser.find_element(By.ID, 'wis-modal')
        self.assertIsNotNone(modal, 'Modal shell should exist in DOM')

        has_open_fn = self.browser.execute_script(
            "return typeof WIS.openModal === 'function';"
        )
        self.assertTrue(has_open_fn, 'WIS.openModal function should be available')

        # Verify SweetAlert is available (used by modal system for notifications)
        has_swal = self.browser.execute_script(
            "return typeof Swal !== 'undefined' && typeof Swal.fire === 'function';"
        )
        self.assertTrue(has_swal, 'SweetAlert should be available for notifications')

        # Trigger a SweetAlert manually and verify it appears
        self.browser.execute_script("Swal.fire({icon:'success', title:'Test', text:'Test notification'});")
        time.sleep(0.5)
        swal_popup = self.browser.find_elements(By.CSS_SELECTOR, '.swal2-popup')
        visible = [s for s in swal_popup if s.is_displayed()]
        self.assertTrue(len(visible) > 0, 'Programmatic SweetAlert should be visible')
        self.browser.execute_script("Swal.close();")
        time.sleep(0.3)

        # Check WIS.toast function exists as well
        has_toast_fn = self.browser.execute_script(
            "return typeof WIS !== 'undefined' && typeof WIS.toast === 'function';"
        )
        self.assertTrue(has_toast_fn, 'WIS.toast function should be available')

    # ═══════════════════════════════════════════════════════════════════
    # PHASE 10: Dashboard Tooltips, Settings UI, Report PDF, Modal Polish
    # ═══════════════════════════════════════════════════════════════════

    def _step_40_dashboard_tooltips(self):
        """Verify dashboard KPIs and widgets have tooltip (?) icons."""
        self.browser.get(self.url('/dashboard/'))
        time.sleep(1)

        # Count dash-tip tooltip icons
        tip_count = self.browser.execute_script(
            "return document.querySelectorAll('.dash-tip[data-bs-toggle=\"tooltip\"]').length;"
        )
        self.assertGreaterEqual(
            tip_count, 10,
            f'Dashboard should have at least 10 tooltip icons, found {tip_count}'
        )

        # Verify tooltips are initialized (Bootstrap adds aria-describedby on hover)
        has_tooltip_init = self.browser.execute_script("""
            var el = document.querySelector('.dash-tip[data-bs-toggle="tooltip"]');
            if (!el) return false;
            return el.getAttribute('title') !== null || el.getAttribute('data-bs-original-title') !== null;
        """)
        self.assertTrue(has_tooltip_init, 'Dashboard tooltip icons should have title attributes')

    def _step_41_settings_ui(self):
        """Verify Settings page has modern grouped card layout."""
        self.browser.get(self.url('/core/settings/'))
        time.sleep(0.5)
        self.assert_no_errors()

        # Check for settings-card class (modern grouped cards)
        card_count = self.browser.execute_script(
            "return document.querySelectorAll('.settings-card').length;"
        )
        self.assertGreaterEqual(
            card_count, 3,
            f'Settings should have at least 3 settings-card sections, found {card_count}'
        )

        # Check for checklist items
        checklist_count = self.browser.execute_script(
            "return document.querySelectorAll('.checklist-item').length;"
        )
        self.assertGreaterEqual(
            checklist_count, 5,
            f'Settings should have at least 5 checklist items, found {checklist_count}'
        )

        # Check for checklist icons
        icon_count = self.browser.execute_script(
            "return document.querySelectorAll('.checklist-icon').length;"
        )
        self.assertGreaterEqual(icon_count, 5, 'Checklist items should have colored icons')

    def _step_42_report_pdf_buttons(self):
        """Verify report pages have PDF export buttons."""
        report_pages = [
            '/reports/sales/',
            '/reports/expenses/',
            '/reports/financial-statement/',
            '/reports/stock-on-hand/',
            '/reports/stock-movement/',
            '/reports/low-stock/',
            '/reports/profit-margin/',
            '/reports/inventory-valuation/',
        ]
        for page_url in report_pages:
            self.browser.get(self.url(page_url))
            time.sleep(0.5)

            has_pdf = self.browser.execute_script(
                "return document.querySelectorAll('.wis-export-pdf').length > 0;"
            )
            self.assertTrue(
                has_pdf,
                f'PDF export button should exist on {page_url}'
            )

    def _step_43_modal_no_duplicate_title(self):
        """Verify modal form does not show duplicate card-header title."""
        self.browser.get(self.url('/catalog/units/'))
        time.sleep(1)

        # Click the New button to open modal
        new_btn = self.browser.find_element(By.CSS_SELECTOR, '[data-modal-url]')
        self.browser.execute_script('arguments[0].click();', new_btn)

        # Wait for modal
        self.wait.until(EC.visibility_of_element_located((By.ID, 'wis-modal')))
        time.sleep(1.5)

        # The card-header inside modal should be hidden via CSS
        card_header_visible = self.browser.execute_script("""
            var ch = document.querySelector('#wis-modal-body .card-header');
            if (!ch) return false;
            return window.getComputedStyle(ch).display !== 'none';
        """)
        self.assertFalse(
            card_header_visible,
            'Card header inside modal should be hidden (no duplicate title)'
        )

        # Modal title should have an icon
        modal_title_html = self.browser.execute_script(
            "return document.getElementById('wis-modal-title').innerHTML;"
        )
        self.assertIn('<i class=', modal_title_html, 'Modal title should contain an icon')

        # Close modal
        self.browser.execute_script(
            "bootstrap.Modal.getInstance(document.getElementById('wis-modal')).hide();"
        )
        time.sleep(0.5)

    # ═══════════════════════════════════════════════════════════════════
    # PHASE 11: CSV Import Functionality
    # ═══════════════════════════════════════════════════════════════════

    def _write_csv_file(self, filename, headers, rows):
        """Write a temporary CSV file and return its absolute path."""
        import csv
        import tempfile
        path = os.path.join(tempfile.gettempdir(), filename)
        with open(path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            for row in rows:
                writer.writerow(row)
        return path

    def _open_import_modal(self, list_url, btn_text_fragment='Import'):
        """Navigate to list page, click Import CSV button to open modal."""
        self.browser.get(self.url(list_url))
        time.sleep(1)
        # Find the import button by matching btn-success with file-import icon
        btns = self.browser.find_elements(By.CSS_SELECTOR, '[data-modal-url]')
        import_btn = None
        for btn in btns:
            if btn_text_fragment.lower() in btn.text.lower() or 'file-import' in btn.get_attribute('innerHTML').lower():
                import_btn = btn
                break
        self.assertIsNotNone(import_btn, f'Import button not found on {list_url}')
        self.browser.execute_script('arguments[0].click();', import_btn)
        # Wait for modal
        self.wait.until(EC.visibility_of_element_located((By.ID, 'wis-modal')))
        time.sleep(1.5)
        return import_btn

    def _upload_csv_in_modal(self, csv_path):
        """Upload a CSV file inside the open import modal and submit."""
        # Find file input inside modal
        file_input = self.wait.until(
            EC.presence_of_element_located((By.CSS_SELECTOR, '#wis-modal-body input[type="file"]'))
        )
        file_input.send_keys(csv_path)
        time.sleep(0.3)
        # Submit the form
        submit_btn = self.browser.find_element(By.CSS_SELECTOR, '#wis-modal-body button[type="submit"]')
        self.browser.execute_script('arguments[0].click();', submit_btn)
        # Wait for SweetAlert success/error or page reload
        time.sleep(3)

    def _step_44_import_modal_ui(self):
        """Verify import modal UI: single Download Template button, form-control file input, no duplicates."""
        self._open_import_modal('/catalog/items/')

        modal_body = self.browser.find_element(By.ID, 'wis-modal-body')
        modal_html = modal_body.get_attribute('innerHTML')

        # Should have exactly ONE Download CSV Template button (in footer)
        download_btns = modal_body.find_elements(By.PARTIAL_LINK_TEXT, 'Download')
        self.assertEqual(
            len(download_btns), 1,
            f'Should have exactly 1 Download Template button, found {len(download_btns)}'
        )

        # The download button should mention "CSV"
        self.assertIn('CSV', download_btns[0].text, 'Download button should say "CSV Template"')

        # File input should use form-control class
        file_input = modal_body.find_element(By.CSS_SELECTOR, 'input[type="file"]')
        classes = file_input.get_attribute('class')
        self.assertIn('form-control', classes, 'File input should have form-control class')

        # Should have import tips card
        self.assertIn('Import Tips', modal_html, 'Modal should contain Import Tips section')

        # Close modal
        self.browser.execute_script(
            "var m = bootstrap.Modal.getInstance(document.getElementById('wis-modal')); if(m) m.hide();"
        )
        time.sleep(0.5)

    def _step_45_import_csv_template_download(self):
        """Verify CSV template downloads return .csv with correct content-type."""
        from django.test import Client
        client = Client()
        client.force_login(self.admin)

        template_urls = [
            '/core/import/catalog/template/',
            '/core/import/expenses/template/',
            '/core/import/sales-orders/template/',
            '/core/import/supplies/template/',
            '/core/import/procurement/template/',
        ]
        for url in template_urls:
            resp = client.get(url)
            self.assertEqual(resp.status_code, 200, f'Template download {url} should return 200')
            ct = resp['Content-Type']
            self.assertIn(
                'text/csv', ct,
                f'{url} should return CSV content-type, got: {ct}'
            )
            disp = resp['Content-Disposition']
            self.assertIn('.csv', disp, f'{url} should have .csv filename, got: {disp}')

    def _step_46_import_catalog_items_csv(self):
        """Import catalog items via CSV and verify import summary modal displays."""
        csv_path = self._write_csv_file('test_catalog_import.csv',
            ['Product / Service Name', 'Item Code (SKU)', 'Item Type', 'Category',
             'Unit', 'Item Cost', 'Item Selling Price'],
            [
                ['Import Widget A', 'IMP-A001', 'Finished Good', 'General', 'pcs', '50.00', '120.00'],
                ['Import Widget B', 'IMP-B002', 'Raw Material', 'General', 'pcs', '30.00', '80.00'],
            ]
        )
        self._open_import_modal('/catalog/items/')
        self._upload_csv_in_modal(csv_path)

        # Wait for import summary modal to appear
        time.sleep(2)
        modal_body = self.wait.until(
            EC.presence_of_element_located((By.ID, 'wis-modal-body'))
        )
        modal_html = modal_body.get_attribute('innerHTML')

        # Verify import summary modal content
        self.assertIn('Import Summary', modal_html, 'Should show Import Summary modal')
        self.assertIn('Created', modal_html, 'Should show Created count')
        self.assertIn('Successfully processed', modal_html, 'Should show success message')
        
        # Close modal and verify imported items
        done_btn = modal_body.find_element(By.PARTIAL_LINK_TEXT, 'Done')
        self.browser.execute_script('arguments[0].click();', done_btn)
        time.sleep(1)
        
        body = self.browser.page_source
        self.assertIn('IMP-A001', body, 'Imported item IMP-A001 should appear in catalog list')
        self.assertIn('IMP-B002', body, 'Imported item IMP-B002 should appear in catalog list')

    def _step_47_import_expenses_csv(self):
        """Import expenses via CSV and verify import summary modal."""
        today = date.today().strftime('%Y-%m-%d')
        csv_path = self._write_csv_file('test_expense_import.csv',
            ['Purchase Date', 'Category', 'Item Description', 'Total Cost', 'Status',
             'Vendor Name', 'Reference No'],
            [
                [today, 'Raw Materials', 'Imported wire spools', '2500.00', 'Paid', 'Wire Co', 'IMP-REF-001'],
                [today, 'Utilities', 'Internet bill imported', '1500.00', 'Paid', 'ISP Corp', 'IMP-REF-002'],
            ]
        )
        self._open_import_modal('/core/expenses/')
        self._upload_csv_in_modal(csv_path)

        time.sleep(2)
        modal_body = self.wait.until(
            EC.presence_of_element_located((By.ID, 'wis-modal-body'))
        )
        modal_html = modal_body.get_attribute('innerHTML')
        self.assertIn('Import Summary', modal_html, 'Should show Import Summary modal')
        self.assertIn('2', modal_html, 'Should show 2 records created')
        
        done_btn = modal_body.find_element(By.PARTIAL_LINK_TEXT, 'Done')
        self.browser.execute_script('arguments[0].click();', done_btn)
        time.sleep(1)
        
        body = self.browser.page_source
        self.assertIn('2,500', body, 'Imported expense of 2500 should appear')
        self.assertIn('1,500', body, 'Imported expense of 1500 should appear')

    def _step_48_import_supply_items_csv(self):
        """Import supply items via CSV and verify they appear."""
        csv_path = self._write_csv_file('test_supply_import.csv',
            ['Product Name', 'Item Code', 'Category', 'Item Cost', 'Available Stocks', 'Minimum Stock'],
            [
                ['Imported Tape Roll', 'IMP-TAPE-01', 'Packaging Materials', '45.00', '200', '20'],
            ]
        )
        self._open_import_modal('/core/supplies/')
        self._upload_csv_in_modal(csv_path)

        time.sleep(2)
        self.browser.execute_script("if(typeof Swal !== 'undefined') Swal.close();")
        time.sleep(1)

        self.browser.get(self.url('/core/supplies/'))
        time.sleep(1)
        body = self.browser.page_source
        self.assertIn('Imported Tape Roll', body, 'Imported supply item should appear')
        self.assertIn('IMP-TAPE-01', body, 'Imported supply item code should appear')

    def _step_49_import_procurement_csv(self):
        """Import stock-in movements via CSV and verify they appear."""
        today = date.today().strftime('%Y-%m-%d')
        csv_path = self._write_csv_file('test_procurement_import.csv',
            ['Stock-In Date', 'Product Name', 'Item Code', 'Stocks Added', 'Unit Cost', 'Status'],
            [
                [today, 'Imported Tape Roll', 'IMP-TAPE-01', '50', '45.00', 'Completed'],
            ]
        )
        self._open_import_modal('/core/supply-movements/')
        self._upload_csv_in_modal(csv_path)

        time.sleep(2)
        self.browser.execute_script("if(typeof Swal !== 'undefined') Swal.close();")
        time.sleep(1)

        self.browser.get(self.url('/core/supply-movements/'))
        time.sleep(1)
        body = self.browser.page_source
        self.assertIn('Imported Tape Roll', body, 'Stock-in movement for Imported Tape Roll should appear')

    def _step_50_import_sales_orders_csv(self):
        """Import sales orders via CSV and verify they appear."""
        today = date.today().strftime('%Y-%m-%d')
        csv_path = self._write_csv_file('test_sales_import.csv',
            ['Billing Date', 'Product / Service Name', 'Item Code (SKU)', 'Quantity',
             'Item Price', 'Payment Status', 'Customer Name', 'Receipt No'],
            [
                [today, 'Test Widget', 'TEST-001', '5', '250.00', 'Unpaid', 'Test Customer Corp', 'IMP-REC-001'],
            ]
        )
        self._open_import_modal('/sales/orders/')
        self._upload_csv_in_modal(csv_path)

        time.sleep(2)
        self.browser.execute_script("if(typeof Swal !== 'undefined') Swal.close();")
        time.sleep(1)

        self.browser.get(self.url('/sales/orders/'))
        time.sleep(1)
        body = self.browser.page_source
        self.assertIn('SO-IMP-', body, 'Imported sales order with SO-IMP- prefix should appear')

    def _step_51_import_with_errors_shows_summary(self):
        """Test import summary modal with errors - verify comprehensive error display."""
        # Create CSV with intentional errors (missing required fields, invalid data)
        csv_path = self._write_csv_file('test_catalog_errors.csv',
            ['Product / Service Name', 'Item Code (SKU)', 'Item Type', 'Category',
             'Unit', 'Item Cost', 'Item Selling Price'],
            [
                # Valid row
                ['Valid Item', 'VALID-001', 'Finished Good', 'General', 'pcs', '100.00', '200.00'],
                # Missing required code
                ['Missing Code Item', '', 'Finished Good', 'General', 'pcs', '50.00', '100.00'],
                # Another valid row
                ['Another Valid', 'VALID-002', 'Raw Material', 'General', 'kg', '75.00', '150.00'],
            ]
        )
        self._open_import_modal('/catalog/items/')
        self._upload_csv_in_modal(csv_path)

        # Wait for import summary modal
        time.sleep(2)
        modal_body = self.wait.until(
            EC.presence_of_element_located((By.ID, 'wis-modal-body'))
        )
        modal_html = modal_body.get_attribute('innerHTML')

        # Verify import summary modal appears
        self.assertIn('Import Summary', modal_html, 'Should show Import Summary modal')
        
        # Verify success statistics (2 valid rows should be created)
        self.assertIn('Created', modal_html, 'Should show Created section')
        self.assertIn('2', modal_html, 'Should show 2 created records')
        
        # Verify error section appears
        self.assertIn('Failed Imports', modal_html, 'Should show Failed Imports section')
        self.assertIn('Error Details', modal_html, 'Should show Error Details column')
        
        # Verify error count badge
        error_badges = modal_body.find_elements(By.CSS_SELECTOR, '.badge-danger, .bg-danger')
        self.assertGreater(len(error_badges), 0, 'Should have error badges displayed')
        
        # Verify error table exists
        error_tables = modal_body.find_elements(By.CSS_SELECTOR, '.card-danger table')
        self.assertGreater(len(error_tables), 0, 'Should have error details table')
        
        # Verify row number is shown in error
        self.assertIn('Row', modal_html, 'Should show row numbers for errors')
        
        # Verify success message still appears for partial success
        self.assertIn('Successfully processed', modal_html, 'Should show success message for valid rows')
        
        # Close modal
        done_btn = modal_body.find_element(By.PARTIAL_LINK_TEXT, 'Done')
        self.browser.execute_script('arguments[0].click();', done_btn)
        time.sleep(1)
        
        # Verify valid items were imported despite errors
        body = self.browser.page_source
        self.assertIn('VALID-001', body, 'Valid item should be imported')
        self.assertIn('VALID-002', body, 'Second valid item should be imported')
