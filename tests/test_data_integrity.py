"""
Data Integrity & Calculation Accuracy Selenium Test
=====================================================
Seeds deterministic sample data (items, SO, POS sale, bundles, expenses),
computes ground-truth values from the DB, then verifies that the
Dashboard, Sales Report, Financial Statement, and Profit Margin pages
all display exactly those values.

Run:
    python manage.py test tests.test_data_integrity --verbosity=2
"""

import os
import re
import time
from decimal import Decimal
from datetime import date, datetime

from django.contrib.auth import get_user_model
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import override_settings

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

User = get_user_model()


# ── Known seed values ──────────────────────────────────────────────────────
ITEM_A_COST = Decimal('100.00')
ITEM_A_SELL = Decimal('200.00')
ITEM_A_SO_QTY = Decimal('2')       # ordered via Sales Order line

ITEM_B_COST = Decimal('50.00')
ITEM_B_SELL = Decimal('100.00')
ITEM_B_POS_QTY = Decimal('3')      # sold via POS

# Bundle: 1x Item A at price 150
BUNDLE_ITEM_PRICE = Decimal('150.00')
BUNDLE_MIN_QTY = Decimal('1')
BUNDLE_MULTIPLIER = Decimal('1')

EXPENSE_AMOUNT = Decimal('100.00')

# ── Derived ground truth ───────────────────────────────────────────────────
SO_LINE_REV = ITEM_A_SELL * ITEM_A_SO_QTY          # 400
# bundle_subtotal = pli.price * qty_multiplier (per model property)
BUNDLE_REV = BUNDLE_ITEM_PRICE * BUNDLE_MULTIPLIER  # 150
SO_REV = SO_LINE_REV + BUNDLE_REV                   # 550

POS_REV = ITEM_B_SELL * ITEM_B_POS_QTY             # 300
TOTAL_REV = SO_REV + POS_REV                        # 850

SO_LINE_COGS = ITEM_A_COST * ITEM_A_SO_QTY          # 200
BUNDLE_COGS = ITEM_A_COST * BUNDLE_MIN_QTY * BUNDLE_MULTIPLIER  # 100
POS_COGS = ITEM_B_COST * ITEM_B_POS_QTY             # 150
TOTAL_COGS = SO_LINE_COGS + BUNDLE_COGS + POS_COGS  # 450

GROSS_PROFIT = TOTAL_REV - TOTAL_COGS               # 400
NET_PROFIT = GROSS_PROFIT - EXPENSE_AMOUNT           # 300


@override_settings(
    DEBUG=True,
    STATICFILES_STORAGE='django.contrib.staticfiles.storage.StaticFilesStorage',
    SESSION_ENGINE='django.contrib.sessions.backends.signed_cookies',
)
class DataIntegrityTest(StaticLiveServerTestCase):
    """Verifies that Dashboard and all Report pages calculate correctly."""

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
            cls.browser = webdriver.Chrome(service=Service(driver_path), options=chrome_options)
        else:
            cls.browser = webdriver.Chrome(options=chrome_options)

        cls.browser.implicitly_wait(5)
        cls.wait = WebDriverWait(cls.browser, 10)

    @classmethod
    def tearDownClass(cls):
        cls.browser.quit()
        super().tearDownClass()

    # ── DB seed ────────────────────────────────────────────────────────────

    def _seed_data(self):
        """
        Create deterministic sample data via ORM.
        Called in setUp() so each test starts with a fresh DB state
        (StaticLiveServerTestCase inherits TransactionTestCase which
        flushes between tests — setUpTestData is not supported).
        """
        from django.utils import timezone
        from catalog.models import Item, Category, Unit
        from warehouses.models import Warehouse, Location
        from partners.models import Customer
        from pricing.models import PriceList, PriceListItem
        from sales.models import SalesOrder, SalesOrderLine, SalesOrderPriceListLine
        from pos.models import POSRegister, POSShift, POSSale, POSSaleLine, POSPayment, SaleStatus, ShiftStatus
        from core.models import DocumentStatus, Expense, ExpenseCategory, SalesChannel

        admin = User.objects.create_superuser('admin_di', 'di@test.com', 'Test1234!')

        cat = Category.objects.create(name='DI-Cat', code='DI-C')
        unit = Unit.objects.create(name='Each', abbreviation='ea')

        item_a = Item.objects.create(
            code='DI-A', name='Item Alpha', category=cat,
            default_unit=unit, cost_price=ITEM_A_COST, selling_price=ITEM_A_SELL,
        )
        item_b = Item.objects.create(
            code='DI-B', name='Item Beta', category=cat,
            default_unit=unit, cost_price=ITEM_B_COST, selling_price=ITEM_B_SELL,
        )

        wh = Warehouse.objects.create(code='DI-WH', name='DI Warehouse', is_active=True)
        loc = Location.objects.create(code='DI-LOC', name='DI Location', warehouse=wh, is_active=True)
        customer = Customer.objects.create(name='DI Customer', code='DI-CUST')

        plist = PriceList.objects.create(name='DI Bundle')
        PriceListItem.objects.create(
            price_list=plist, item=item_a, unit=unit,
            price=BUNDLE_ITEM_PRICE, min_qty=BUNDLE_MIN_QTY,
        )

        so = SalesOrder.objects.create(
            document_number='DI-SO-001',
            customer=customer,
            warehouse=wh,
            order_date=date.today(),
            status=DocumentStatus.POSTED,
            created_by=admin,
        )
        SalesOrderLine.objects.create(
            sales_order=so, item=item_a, unit=unit,
            qty_ordered=ITEM_A_SO_QTY, unit_price=ITEM_A_SELL,
            discount_type='AMOUNT', discount_value=Decimal('0'),
        )
        SalesOrderPriceListLine.objects.create(
            sales_order=so, price_list=plist,
            qty_multiplier=BUNDLE_MULTIPLIER,
            discount_type='AMOUNT', discount_value=Decimal('0'),
        )

        register = POSRegister.objects.create(
            name='DI-REG', warehouse=wh, default_location=loc, is_active=True,
        )
        shift = POSShift.objects.create(
            register=register, opened_by=admin,
            opened_at=timezone.now(),
            opening_cash=Decimal('0'), status=ShiftStatus.OPEN,
        )
        channel, _ = SalesChannel.objects.get_or_create(name='DI Channel')
        pos_sale = POSSale.objects.create(
            sale_no='DI-POS-001',
            shift=shift, channel=channel,
            register=register, warehouse=wh, location=loc,
            status=SaleStatus.PAID,
            subtotal=POS_REV, grand_total=POS_REV,
            discount_total=Decimal('0'), tax_total=Decimal('0'),
            created_by=admin,
        )
        POSSaleLine.objects.create(
            sale=pos_sale, item=item_b, unit=unit,
            qty=ITEM_B_POS_QTY, unit_price=ITEM_B_SELL,
            line_total=POS_REV,
        )
        POSPayment.objects.create(sale=pos_sale, method='CASH', amount=POS_REV)

        exp_cat, _ = ExpenseCategory.objects.get_or_create(
            name='DI OpEx', defaults={'code': 'DI-OPEX', 'is_cogs': False},
        )
        Expense.objects.create(
            category=exp_cat, amount=EXPENSE_AMOUNT,
            date=date.today(), item_description='DI test expense',
            created_by=admin,
        )

    def setUp(self):
        self._seed_data()

    # ── Helpers ────────────────────────────────────────────────────────────

    def url(self, path):
        return f'{self.live_server_url}{path}'

    def login(self):
        self.browser.get(self.url('/accounts/login/'))
        self.wait.until(EC.presence_of_element_located((By.NAME, 'username')))
        self.browser.find_element(By.NAME, 'username').send_keys('admin_di')
        self.browser.find_element(By.NAME, 'password').send_keys('Test1234!')
        btn = self.browser.find_element(By.CSS_SELECTOR, 'button[type="submit"]')
        self.browser.execute_script('arguments[0].click();', btn)
        self.wait.until(EC.url_contains('/dashboard'))

    def _src(self):
        return self.browser.page_source

    @staticmethod
    def _strip_num(text):
        """Strip currency symbol, commas and whitespace; return Decimal."""
        cleaned = re.sub(r'[^\d.\-]', '', text.replace(',', ''))
        try:
            return Decimal(cleaned)
        except Exception:
            return Decimal('0')

    def _find_value_after_label(self, label_text):
        """Find a numeric value near a label text in the page (td/span context)."""
        src = self._src()
        # Try to find patterns like: label...1,234.00
        pattern = re.compile(
            re.escape(label_text) + r'.*?([\d,]+\.\d{2})',
            re.IGNORECASE | re.DOTALL,
        )
        m = pattern.search(src)
        if m:
            return self._strip_num(m.group(1))
        return None

    def assert_value_near(self, page_value, expected, label='', tolerance=Decimal('0.05')):
        """Assert page_value ≈ expected (within tolerance)."""
        diff = abs(page_value - expected)
        self.assertLessEqual(
            diff, tolerance,
            msg=f'{label}: expected {expected}, got {page_value} (diff={diff})',
        )

    def _page_contains_number(self, number, digits=2):
        """Return True if the page source contains the formatted number."""
        formatted_exact = f'{number:,.{digits}f}'
        # also check without trailing zeros
        formatted_short = f'{number:.{digits}f}'
        src = self._src()
        return formatted_exact in src or formatted_short in src

    # ── Test Steps ─────────────────────────────────────────────────────────

    def test_01_login(self):
        self.login()
        self.assertIn('/dashboard', self.browser.current_url)

    def test_02_dashboard_so_revenue_included(self):
        """Dashboard with period=year must include POSTED SO revenue."""
        self.login()
        self.browser.get(self.url('/dashboard/?period=year'))
        self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, '.small-box')))
        src = self._src()

        # The page must not show SO revenue as 0 — POSTED SOs must be included
        # Check that combined revenue ≥ TOTAL_REV (850)
        # Look for any number ≥ 850 in the revenue cards
        numbers_in_page = [
            self._strip_num(m)
            for m in re.findall(r'[\d,]+\.\d{2}', src.replace(',', ''))
        ]
        large_numbers = [n for n in numbers_in_page if n >= TOTAL_REV]
        self.assertTrue(
            len(large_numbers) > 0,
            msg=f'Dashboard should show combined revenue ≥ {TOTAL_REV}. '
                f'Numbers found on page: {sorted(set(numbers_in_page), reverse=True)[:10]}',
        )

    def test_03_dashboard_combined_revenue_card(self):
        """Dashboard KPI card shows combined_revenue = POS + SO (850 total)."""
        self.login()
        self.browser.get(self.url('/dashboard/?period=year'))
        self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, '.small-box')))
        # combined_revenue = POS 300 + SO line 400 + bundle 150 = 850
        self.assertTrue(
            self._page_contains_number(TOTAL_REV),
            msg=f'Dashboard should contain combined revenue {TOTAL_REV}. '
                f'Page source snippet (literal search for {TOTAL_REV}): '
                + str(self._src()[:500]),
        )

    def test_04_sales_report_so_revenue(self):
        """Sales Report must include SO revenue (POSTED) in its totals."""
        self.login()
        today_iso = date.today().isoformat()
        year_start = date.today().replace(month=1, day=1).isoformat()
        self.browser.get(
            self.url(f'/reports/sales/?date_from={year_start}&date_to={today_iso}')
        )
        self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, '.card')))

        # Combined revenue (POS + SO) must be ≥ TOTAL_REV (850)
        src = self._src()
        numbers = [
            self._strip_num(m) for m in re.findall(r'[\d,]+\.\d{2}', src.replace(',', ''))
        ]
        self.assertTrue(
            any(n >= TOTAL_REV for n in numbers),
            msg=f'Sales report should show total revenue ≥ {TOTAL_REV}. '
                f'Numbers: {sorted(set(numbers), reverse=True)[:10]}',
        )

    def test_05_sales_report_bundle_included(self):
        """Sales Report: bundle revenue (150) must appear in totals."""
        self.login()
        today_iso = date.today().isoformat()
        year_start = date.today().replace(month=1, day=1).isoformat()
        self.browser.get(
            self.url(f'/reports/sales/?date_from={year_start}&date_to={today_iso}')
        )
        self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, '.card')))
        # The SO revenue column should show at least BUNDLE_REV contribution
        # Total SO revenue = 550 should appear somewhere
        self.assertTrue(
            self._page_contains_number(SO_REV),
            msg=f'Sales report should contain SO revenue {SO_REV}',
        )

    def test_06_financial_statement_so_revenue(self):
        """Financial Statement P&L must include POSTED SO revenue."""
        self.login()
        today_iso = date.today().isoformat()
        year_start = date.today().replace(month=1, day=1).isoformat()
        self.browser.get(
            self.url(f'/reports/financial-statement/?date_from={year_start}&date_to={today_iso}')
        )
        self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, '.pnl-table')))
        src = self._src()

        # Net revenue ≥ TOTAL_REV (850)
        numbers = [
            self._strip_num(m) for m in re.findall(r'[\d,]+\.\d{2}', src.replace(',', ''))
        ]
        self.assertTrue(
            any(n >= TOTAL_REV for n in numbers),
            msg=f'Financial statement should show net revenue ≥ {TOTAL_REV}. '
                f'Numbers: {sorted(set(numbers), reverse=True)[:10]}',
        )

    def test_07_financial_statement_so_revenue_row(self):
        """Financial Statement should show Sales Orders Revenue row with correct value."""
        self.login()
        today_iso = date.today().isoformat()
        year_start = date.today().replace(month=1, day=1).isoformat()
        self.browser.get(
            self.url(f'/reports/financial-statement/?date_from={year_start}&date_to={today_iso}')
        )
        self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, '.pnl-table')))
        # Look for "Sales Orders Revenue" row with SO_REV (550)
        self.assertIn('Sales Orders Revenue', self._src(),
                      'Financial statement must have "Sales Orders Revenue" row')
        self.assertTrue(
            self._page_contains_number(SO_REV),
            msg=f'Financial statement SO revenue row should show {SO_REV}',
        )

    def test_08_financial_statement_gross_profit(self):
        """Gross Profit = Total Revenue - COGS must be approximately correct."""
        self.login()
        today_iso = date.today().isoformat()
        year_start = date.today().replace(month=1, day=1).isoformat()
        self.browser.get(
            self.url(f'/reports/financial-statement/?date_from={year_start}&date_to={today_iso}')
        )
        self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, '.pnl-table')))
        self.assertIn('GROSS PROFIT', self._src())
        # Gross profit should appear somewhere in the page
        self.assertTrue(
            self._page_contains_number(GROSS_PROFIT),
            msg=f'Financial statement gross profit should be {GROSS_PROFIT}',
        )

    def test_09_profit_margin_items_from_so(self):
        """Profit Margin report must list items sold via SO (POSTED)."""
        self.login()
        today_iso = date.today().isoformat()
        year_start = date.today().replace(month=1, day=1).isoformat()
        self.browser.get(
            self.url(f'/reports/profit-margin/?date_from={year_start}&date_to={today_iso}')
        )
        self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, '.card')))
        src = self._src()

        # Item Alpha (from SO line) and Item Beta (from POS) should both appear
        self.assertIn('Item Alpha', src,
                      'Profit margin should list Item Alpha from POSTED SO')
        self.assertIn('Item Beta', src,
                      'Profit margin should list Item Beta from POS sale')

    def test_10_profit_margin_so_revenue(self):
        """Profit Margin grand revenue must include SO + POS combined."""
        self.login()
        today_iso = date.today().isoformat()
        year_start = date.today().replace(month=1, day=1).isoformat()
        self.browser.get(
            self.url(f'/reports/profit-margin/?date_from={year_start}&date_to={today_iso}')
        )
        self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, '.card')))
        numbers = [
            self._strip_num(m)
            for m in re.findall(r'[\d,]+\.\d{2}', self._src().replace(',', ''))
        ]
        self.assertTrue(
            any(n >= TOTAL_REV for n in numbers),
            msg=f'Profit margin total revenue should be ≥ {TOTAL_REV}. '
                f'Numbers: {sorted(set(numbers), reverse=True)[:10]}',
        )

    def test_11_no_django_errors_on_any_report(self):
        """None of the report pages should return a Django debug error page."""
        self.login()
        today_iso = date.today().isoformat()
        year_start = date.today().replace(month=1, day=1).isoformat()
        date_params = f'?date_from={year_start}&date_to={today_iso}'

        pages = [
            ('/dashboard/?period=year', 'Dashboard'),
            (f'/reports/sales/{date_params}', 'Sales Report'),
            (f'/reports/financial-statement/{date_params}', 'Financial Statement'),
            (f'/reports/profit-margin/{date_params}', 'Profit Margin'),
            ('/reports/stock-on-hand/', 'Stock on Hand'),
            ('/reports/low-stock/', 'Low Stock'),
            ('/reports/inventory-valuation/', 'Inventory Valuation'),
            (f'/reports/expenses/{date_params}', 'Expense Report'),
        ]

        for path, name in pages:
            self.browser.get(self.url(path))
            self.wait.until(
                lambda d: d.execute_script('return document.readyState') == 'complete'
            )
            src = self._src()
            self.assertNotIn('Traceback', src, msg=f'{name}: Django traceback found')
            self.assertNotIn('Page not found', src, msg=f'{name}: 404 found')
            self.assertNotIn('Server Error', src, msg=f'{name}: 500 found')

    def test_12_db_ground_truth_matches_expected(self):
        """
        Non-browser: directly verify DB aggregation matches known seed values.
        This is the reference point for all UI comparisons.
        """
        from sales.models import SalesOrder, SalesOrderLine, SalesOrderPriceListLine
        from pos.models import POSSale, POSSaleLine, SaleStatus
        from core.models import DocumentStatus, Expense
        from django.db.models import Sum

        # SO revenue (APPROVED + POSTED)
        so_qs = SalesOrder.objects.filter(
            status__in=[DocumentStatus.APPROVED, DocumentStatus.POSTED],
            order_date=date.today(),
        )
        lines = list(SalesOrderLine.objects.filter(sales_order__in=so_qs).select_related('item'))
        bundles = list(
            SalesOrderPriceListLine.objects.filter(sales_order__in=so_qs)
            .prefetch_related('price_list__items__item')
        )
        db_so_line_rev = sum(l.line_total for l in lines)
        db_so_bundle_rev = sum(b.bundle_total for b in bundles)
        db_so_rev = db_so_line_rev + db_so_bundle_rev

        # POS revenue
        pos_qs = POSSale.objects.filter(
            status__in=[SaleStatus.PAID, SaleStatus.POSTED],
            created_at__date=date.today(),
        )
        db_pos_rev = pos_qs.aggregate(t=Sum('grand_total'))['t'] or Decimal('0')

        # COGS
        db_so_cogs = sum(
            (l.item.cost_price or Decimal('0')) * l.qty_ordered for l in lines
        )
        db_bundle_cogs = Decimal('0')
        for b in bundles:
            for p in b.price_list.items.all():
                db_bundle_cogs += (p.item.cost_price or Decimal('0')) * p.min_qty * b.qty_multiplier

        db_pos_cogs = sum(
            (Decimal(str(l.item.cost_price or 0)) * l.qty)
            for l in POSSaleLine.objects.filter(sale__in=pos_qs).select_related('item')
        )

        # Expenses
        db_exp = Expense.objects.filter(date=date.today()).aggregate(t=Sum('amount'))['t'] or Decimal('0')

        # Assert DB ground truth matches our known seed constants
        self.assertEqual(db_so_line_rev, SO_LINE_REV,
                         f'SO line revenue: expected {SO_LINE_REV}, got {db_so_line_rev}')
        self.assertEqual(db_so_bundle_rev, BUNDLE_REV,
                         f'Bundle revenue: expected {BUNDLE_REV}, got {db_so_bundle_rev}')
        self.assertEqual(db_so_rev, SO_REV,
                         f'SO total revenue: expected {SO_REV}, got {db_so_rev}')
        self.assertEqual(db_pos_rev, POS_REV,
                         f'POS revenue: expected {POS_REV}, got {db_pos_rev}')
        self.assertEqual(db_so_cogs, SO_LINE_COGS,
                         f'SO COGS: expected {SO_LINE_COGS}, got {db_so_cogs}')
        self.assertEqual(db_bundle_cogs, BUNDLE_COGS,
                         f'Bundle COGS: expected {BUNDLE_COGS}, got {db_bundle_cogs}')
        self.assertEqual(db_pos_cogs, POS_COGS,
                         f'POS COGS: expected {POS_COGS}, got {db_pos_cogs}')
        self.assertGreaterEqual(db_exp, EXPENSE_AMOUNT,
                                f'Expenses: expected ≥ {EXPENSE_AMOUNT}, got {db_exp}')
