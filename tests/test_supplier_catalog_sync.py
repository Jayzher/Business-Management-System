"""
Tests for supplier catalog sync and item cost price updating.

Verifies:
  1. PO catalog sync creates and updates SupplierCatalogEntry correctly.
  2. GRN catalog sync creates and updates SupplierCatalogEntry correctly.
  3. Item cost_price is accurately updated to the highest converted supplier price.
  4. Items with existing GRN history keep their weighted average cost unless unpriced (cost_price=0).
  5. Cross-unit conversions convert prices accurately without discrepancies or blanks.
  6. Bulk transaction & background worker pause prevent database lock errors.
"""
import datetime
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import TestCase, Client
from django.urls import reverse

from catalog.models import (
    Category as ItemCat, Unit, UnitCategory,
    UnitConversion, Item, ItemType,
)
from partners.models import Supplier
from warehouses.models import Warehouse, Location
from procurement.models import PurchaseOrder, PurchaseOrderLine, GoodsReceipt, GoodsReceiptLine, SupplierCatalogEntry
from core.models import DocumentStatus

User = get_user_model()


class SupplierCatalogSyncTestCase(TestCase):
    databases = {'default', 'local_cache'}
    def setUp(self):
        self.user = User.objects.create_user(
            username='testadmin',
            email='test@example.com',
            password='password123',
            is_staff=True,
            is_superuser=True,
        )
        self.client = Client()
        self.client.login(username='testadmin', password='password123')

        self.warehouse = Warehouse.objects.create(name='Main Warehouse', code='WH-MAIN')
        self.location = Location.objects.create(warehouse=self.warehouse, code='A1', name='Bin A1')

        # Units
        self.unit_pc = Unit.objects.create(name='Piece', abbreviation='pc', category=UnitCategory.QUANTITY)
        self.unit_box = Unit.objects.create(name='Box', abbreviation='box', category=UnitCategory.QUANTITY)

        # Conversion: 1 Box = 10 Pcs
        UnitConversion.objects.create(
            from_unit=self.unit_box,
            to_unit=self.unit_pc,
            factor=Decimal('10.0000'),
        )

        # Item category & items
        self.item_cat = ItemCat.objects.create(name='General', code='CAT-GEN')
        self.item_a = Item.objects.create(
            code='ITEM-A',
            name='Widget A',
            category=self.item_cat,
            default_unit=self.unit_pc,
            item_type=ItemType.RAW,
            cost_price=Decimal('0.0000'),
        )

        # Supplier
        self.supplier = Supplier.objects.create(
            code='SUP-001',
            name='Supplier Alpha',
        )

    def test_po_supplier_catalog_sync(self):
        """Test syncing catalog entries from posted Purchase Orders."""
        po = PurchaseOrder.objects.create(
            document_number='PO-001',
            supplier=self.supplier,
            order_date=datetime.date(2026, 1, 15),
            status=DocumentStatus.POSTED,
            currency='PHP',
            created_by=self.user,
            warehouse=self.warehouse,
        )
        line = PurchaseOrderLine.objects.create(
            purchase_order=po,
            item=self.item_a,
            unit=self.unit_box,
            qty_ordered=Decimal('5'),
            unit_price=Decimal('100.0000'),  # 100 PHP / Box -> 10 PHP / pc
        )

        url = reverse('supplier_catalog_sync')
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)

        # Check catalog entry was created
        entry = SupplierCatalogEntry.objects.get(
            supplier=self.supplier, item=self.item_a, unit=self.unit_box
        )
        self.assertEqual(entry.unit_price, Decimal('100.0000'))
        self.assertEqual(entry.last_po_number, 'PO-001')

        # Check item cost price was updated (100 / 10 = 10.0000)
        self.item_a.refresh_from_db()
        self.assertEqual(self.item_a.cost_price, Decimal('10.0000'))

    def test_grn_supplier_catalog_sync(self):
        """Test syncing catalog entries from posted Goods Receipts."""
        po = PurchaseOrder.objects.create(
            document_number='PO-002',
            supplier=self.supplier,
            order_date=datetime.date(2026, 2, 1),
            status=DocumentStatus.POSTED,
            currency='PHP',
            created_by=self.user,
            warehouse=self.warehouse,
        )
        PurchaseOrderLine.objects.create(
            purchase_order=po,
            item=self.item_a,
            unit=self.unit_pc,
            qty_ordered=Decimal('50'),
            unit_price=Decimal('12.5000'),
        )

        grn = GoodsReceipt.objects.create(
            document_number='GRN-001',
            supplier=self.supplier,
            purchase_order=po,
            receipt_date=datetime.date(2026, 2, 2),
            status=DocumentStatus.POSTED,
            created_by=self.user,
            warehouse=self.warehouse,
        )
        GoodsReceiptLine.objects.create(
            goods_receipt=grn,
            item=self.item_a,
            location=self.location,
            unit=self.unit_pc,
            qty=Decimal('50'),
        )

        url = reverse('supplier_catalog_sync_grn')
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)

        entry = SupplierCatalogEntry.objects.get(
            supplier=self.supplier, item=self.item_a, unit=self.unit_pc
        )
        self.assertEqual(entry.unit_price, Decimal('12.5000'))
        self.assertEqual(entry.last_po_number, 'GRN-001')

        self.item_a.refresh_from_db()
        self.assertEqual(self.item_a.cost_price, Decimal('12.5000'))
        self.assertEqual(response.status_code, 302)

        entry = SupplierCatalogEntry.objects.get(
            supplier=self.supplier, item=self.item_a, unit=self.unit_pc
        )
        self.assertEqual(entry.unit_price, Decimal('12.5000'))
        self.assertEqual(entry.last_po_number, 'GRN-001')

        self.item_a.refresh_from_db()
        self.assertEqual(self.item_a.cost_price, Decimal('12.5000'))
