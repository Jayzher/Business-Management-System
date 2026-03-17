"""
Tests for:
  1. Invoice.grand_total_cogs field exists + sync_invoice_cogs command
  2. SO detail view passes COGS context (line_cogs_map, grand_total_cogs)
  3. SO detail template renders Grand Total + COGS summary
  4. Financial statement view passes breakdown_rows
  5. Financial statement template renders Computation Breakdown button + modal
  6. Custom template filters: get_item, subtract
"""
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from decimal import Decimal
from django.test import TestCase, RequestFactory
from django.contrib.auth import get_user_model
from django.test import Client

User = get_user_model()


class InvoiceCOGSFieldTest(TestCase):
    """Invoice model has grand_total_cogs field."""

    def test_field_exists(self):
        from core.models import Invoice
        self.assertTrue(hasattr(Invoice, 'grand_total_cogs'))
        # field defaults to 0
        from django.db import connection
        cols = [c.name for c in connection.introspection.get_table_description(
            connection.cursor(), 'core_invoice')]
        self.assertIn('grand_total_cogs', cols)


class SyncInvoiceCOGSCommandTest(TestCase):
    """sync_invoice_cogs management command runs without errors."""

    def _setup_user(self):
        return User.objects.create_superuser('test_sync_u', 'x@x.com', 'pass1234')

    def test_command_dry_run(self):
        from django.core.management import call_command
        from io import StringIO
        out = StringIO()
        call_command('sync_invoice_cogs', dry_run=True, stdout=out)
        output = out.getvalue()
        # Should end with dry-run complete message
        self.assertIn('Dry-run', output)

    def test_command_live(self):
        from django.core.management import call_command
        from io import StringIO
        out = StringIO()
        call_command('sync_invoice_cogs', stdout=out)
        output = out.getvalue()
        self.assertIn('Sync complete', output)


class CustomFiltersTest(TestCase):
    """get_item and subtract custom template filters work correctly."""

    def test_get_item_filter(self):
        from theme.templatetags.custom_filters import get_item
        d = {1: Decimal('100'), 2: Decimal('200')}
        self.assertEqual(get_item(d, 1), Decimal('100'))
        self.assertIsNone(get_item(d, 99))
        self.assertIsNone(get_item('not-a-dict', 1))

    def test_subtract_filter(self):
        from theme.templatetags.custom_filters import subtract
        result = subtract(Decimal('500'), Decimal('200'))
        self.assertEqual(result, Decimal('300'))
        result2 = subtract('1000', '350')
        self.assertEqual(result2, Decimal('650'))


class SODetailCOGSViewTest(TestCase):
    """SO detail view returns correct COGS context."""

    @classmethod
    def setUpTestData(cls):
        from catalog.models import Item, Category, Unit
        from partners.models import Customer
        from warehouses.models import Warehouse, Location
        from sales.models import SalesOrder, SalesOrderLine
        from core.models import DocumentStatus

        cls.user = User.objects.create_superuser('so_cogs_u', 'a@b.com', 'pass1234')

        cat = Category.objects.create(name='TestCat')
        cls.unit = Unit.objects.create(name='Piece', abbreviation='pc')
        cls.item = Item.objects.create(
            code='TITM01', name='Test Item',
            category=cat, default_unit=cls.unit,
            cost_price=Decimal('50.00'),
            selling_price=Decimal('100.00'),
        )
        cls.customer = Customer.objects.create(name='Test Cust', code='TC01')
        cls.wh = Warehouse.objects.create(name='WH1', code='WH1')
        cls.loc = Location.objects.create(name='Main', code='MAIN', warehouse=cls.wh)

        import datetime
        cls.so = SalesOrder.objects.create(
            document_number='TSO-COGS-001',
            status=DocumentStatus.APPROVED,
            customer=cls.customer,
            warehouse=cls.wh,
            order_date=datetime.date.today(),
            created_by=cls.user,
        )
        cls.sol = SalesOrderLine.objects.create(
            sales_order=cls.so,
            item=cls.item,
            qty_ordered=Decimal('3'),
            unit=cls.unit,
            unit_price=Decimal('100.00'),
        )

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.user)

    def test_so_detail_returns_200(self):
        from django.urls import reverse
        url = reverse('sales_order_detail', args=[self.so.pk])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

    def test_so_detail_has_cogs_context(self):
        from django.urls import reverse
        url = reverse('sales_order_detail', args=[self.so.pk])
        resp = self.client.get(url)
        self.assertIn('line_cogs_map', resp.context)
        self.assertIn('grand_total_cogs', resp.context)
        # COGS = cost_price × qty_ordered = 50 × 3 = 150
        self.assertEqual(resp.context['grand_total_cogs'], Decimal('150.00'))
        self.assertEqual(resp.context['so_line_cogs_total'], Decimal('150.00'))

    def test_so_detail_line_cogs_map(self):
        from django.urls import reverse
        url = reverse('sales_order_detail', args=[self.so.pk])
        resp = self.client.get(url)
        cogs_map = resp.context['line_cogs_map']
        self.assertIn(self.sol.pk, cogs_map)
        self.assertEqual(cogs_map[self.sol.pk], Decimal('150.00'))

    def test_so_detail_grand_total(self):
        from django.urls import reverse
        url = reverse('sales_order_detail', args=[self.so.pk])
        resp = self.client.get(url)
        content = resp.content.decode()
        # Grand Total (Revenue) should appear
        self.assertIn('Grand Total (Revenue)', content)
        # Grand Total COGS should appear
        self.assertIn('Grand Total COGS', content)
        # Gross Profit should appear
        self.assertIn('Gross Profit', content)

    def test_so_detail_unit_price_not_catalog(self):
        """unit_price displayed is from the SO line, not catalog selling_price."""
        from django.urls import reverse
        # Change catalog price to something different
        self.item.selling_price = Decimal('999.00')
        self.item.save()
        url = reverse('sales_order_detail', args=[self.so.pk])
        resp = self.client.get(url)
        content = resp.content.decode()
        # Should show line unit_price (100), NOT catalog price (999)
        self.assertIn('100.00', content)
        # Restore
        self.item.selling_price = Decimal('100.00')
        self.item.save()


class FinancialStatementBreakdownTest(TestCase):
    """Financial statement view passes breakdown_rows and template renders modal."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_superuser('fs_bd_u', 'b@c.com', 'pass1234')

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.user)

    def test_financial_statement_returns_200(self):
        from django.urls import reverse
        resp = self.client.get(reverse('report_financial_statement'))
        self.assertEqual(resp.status_code, 200)

    def test_breakdown_rows_in_context(self):
        from django.urls import reverse
        resp = self.client.get(reverse('report_financial_statement'))
        self.assertIn('breakdown_rows', resp.context)
        self.assertIn('breakdown_total_revenue', resp.context)
        self.assertIn('breakdown_total_cogs', resp.context)
        self.assertIn('breakdown_total_gp', resp.context)

    def test_breakdown_button_in_html(self):
        from django.urls import reverse
        resp = self.client.get(reverse('report_financial_statement'))
        content = resp.content.decode()
        self.assertIn('breakdownModal', content)
        self.assertIn('Computation Breakdown', content)

    def test_breakdown_modal_in_html(self):
        from django.urls import reverse
        resp = self.client.get(reverse('report_financial_statement'))
        content = resp.content.decode()
        self.assertIn('id="breakdownModal"', content)
        # Table headers
        self.assertIn('Revenue', content)
        self.assertIn('COGS', content)
        self.assertIn('Gross Profit', content)


if __name__ == '__main__':
    import unittest
    unittest.main()
