from datetime import date
from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model

from catalog.models import Category, Unit, Item
from partners.models import Supplier
from procurement.models import (
    PurchaseOrder, PurchaseOrderLine, SupplierCatalogEntry,
    GoodsReceipt, GoodsReceiptLine,
)
from warehouses.models import Warehouse, Location

User = get_user_model()


class SupplierCatalogSyncTests(TestCase):
    databases = '__all__'

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='procurement_admin',
            password='password123',
            is_staff=True,
            is_superuser=True,
        )
        self.client.login(username='procurement_admin', password='password123')

        self.category = Category.objects.create(name='Hardware', code='HW')
        self.unit = Unit.objects.create(name='Piece', abbreviation='pc')

        self.item1 = Item.objects.create(
            code='ITEM-001',
            name='Hammer',
            category=self.category,
            default_unit=self.unit,
            cost_price=Decimal('10.00'),
        )
        self.item2 = Item.objects.create(
            code='ITEM-002',
            name='Screwdriver',
            category=self.category,
            default_unit=self.unit,
            cost_price=Decimal('5.00'),
        )

        self.supplier = Supplier.objects.create(name='Acme Tools', code='ACME')
        self.warehouse = Warehouse.objects.create(code='WH-01', name='Main Warehouse')

        self.po = PurchaseOrder.objects.create(
            supplier=self.supplier,
            warehouse=self.warehouse,
            created_by=self.user,
            status='POSTED',
            currency='PHP',
            order_date='2026-08-01',
        )

        self.po_line1 = PurchaseOrderLine.objects.create(
            purchase_order=self.po,
            item=self.item1,
            unit=self.unit,
            qty_ordered=Decimal('10'),
            unit_price=Decimal('25.00'),
        )
        self.po_line2 = PurchaseOrderLine.objects.create(
            purchase_order=self.po,
            item=self.item2,
            unit=self.unit,
            qty_ordered=Decimal('5'),
            unit_price=Decimal('15.00'),
        )

    def test_sync_prompt_get_displays_candidate_items(self):
        url = reverse('supplier_catalog_sync')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn('items_list', response.context)
        items_list = response.context['items_list']
        self.assertEqual(len(items_list), 2)
        item_ids = [entry['item'].id for entry in items_list]
        self.assertIn(self.item1.id, item_ids)
        self.assertIn(self.item2.id, item_ids)

    def test_sync_creates_catalog_entries_without_touching_cost_price(self):
        url = reverse('supplier_catalog_sync')
        # Select item1 only
        data = {
            'selected_items': [str(self.item1.id)],
        }
        response = self.client.post(url, data, follow=True)
        self.assertEqual(response.status_code, 200)

        # SupplierCatalogEntry should be created for item1 with price 25.00
        entry1 = SupplierCatalogEntry.objects.filter(supplier=self.supplier, item=self.item1).first()
        self.assertIsNotNone(entry1)
        self.assertEqual(entry1.unit_price, Decimal('25.00'))

        # item2 was not selected, so no catalog entry for item2
        entry2 = SupplierCatalogEntry.objects.filter(supplier=self.supplier, item=self.item2).first()
        self.assertIsNone(entry2)

        # Item cost prices are never touched by this sync anymore
        self.item1.refresh_from_db()
        self.assertEqual(self.item1.cost_price, Decimal('10.00'))

    def test_sync_never_updates_item_cost_price(self):
        url = reverse('supplier_catalog_sync')
        # Select item1 and item2
        data = {
            'selected_items': [str(self.item1.id), str(self.item2.id)],
        }
        response = self.client.post(url, data, follow=True)
        self.assertEqual(response.status_code, 200)

        # SupplierCatalogEntry created for both
        entry1 = SupplierCatalogEntry.objects.filter(supplier=self.supplier, item=self.item1).first()
        entry2 = SupplierCatalogEntry.objects.filter(supplier=self.supplier, item=self.item2).first()
        self.assertIsNotNone(entry1)
        self.assertIsNotNone(entry2)
        self.assertEqual(entry1.unit_price, Decimal('25.00'))
        self.assertEqual(entry2.unit_price, Decimal('15.00'))

        # Item cost_price must remain exactly as it was before the sync
        self.item1.refresh_from_db()
        self.item2.refresh_from_db()
        self.assertEqual(self.item1.cost_price, Decimal('10.00'))
        self.assertEqual(self.item2.cost_price, Decimal('5.00'))

        # The result page reports the changes so they can be reviewed
        changes = response.context['changes']
        changed_item_ids = {c['item'].id for c in changes}
        self.assertIn(self.item1.id, changed_item_ids)
        self.assertIn(self.item2.id, changed_item_ids)

    def test_sync_no_items_selected_shows_warning(self):
        url = reverse('supplier_catalog_sync')
        data = {
            'selected_items': [],
        }
        response = self.client.post(url, data, follow=True)
        self.assertEqual(response.status_code, 200)

        # No entries created
        self.assertEqual(SupplierCatalogEntry.objects.count(), 0)

    def test_sync_uses_grn_price_when_available(self):
        # item1's PO line is priced at 25.00, dated 2026-08-01. A GRN
        # received later (2026-08-03) borrows that same PO price but is
        # recorded (and reported) as coming from the GRN, since GRNs are
        # now the source of truth whenever a posted GRN exists.
        location = Location.objects.create(warehouse=self.warehouse, code='LOC-01', name='Main Location')
        grn = GoodsReceipt.objects.create(
            purchase_order=self.po,
            supplier=self.supplier,
            warehouse=self.warehouse,
            created_by=self.user,
            status='POSTED',
            receipt_date=date(2026, 8, 3),
        )
        GoodsReceiptLine.objects.create(
            goods_receipt=grn,
            item=self.item1,
            location=location,
            qty=Decimal('10'),
            unit=self.unit,
        )

        url = reverse('supplier_catalog_sync')
        response = self.client.post(url, {'selected_items': [str(self.item1.id)]}, follow=True)
        self.assertEqual(response.status_code, 200)

        entry1 = SupplierCatalogEntry.objects.get(supplier=self.supplier, item=self.item1)
        self.assertEqual(entry1.unit_price, Decimal('25.00'))
        self.assertEqual(entry1.last_po_number, grn.document_number)

        changes = response.context['changes']
        change = next(c for c in changes if c['item'].id == self.item1.id)
        self.assertEqual(change['source'], 'GRN')

    def test_sync_grn_wins_even_over_a_newer_po_price(self):
        # item2's original PO line is priced at 15.00 (2026-08-01) and
        # received via a GRN on 2026-08-02 (still 15.00, borrowed from that
        # PO line). A SECOND, later PO (2026-08-05) reprices item2 to 20.00
        # but is never received. Because GRN data is the source of truth —
        # not just "most recent" — the catalog must keep the GRN's 15.00,
        # even though the unreceived PO is chronologically newer.
        location = Location.objects.create(warehouse=self.warehouse, code='LOC-01', name='Main Location')
        grn = GoodsReceipt.objects.create(
            purchase_order=self.po,
            supplier=self.supplier,
            warehouse=self.warehouse,
            created_by=self.user,
            status='POSTED',
            receipt_date=date(2026, 8, 2),
        )
        GoodsReceiptLine.objects.create(
            goods_receipt=grn,
            item=self.item2,
            location=location,
            qty=Decimal('5'),
            unit=self.unit,
        )

        later_po = PurchaseOrder.objects.create(
            document_number='PO-LATER-001',
            supplier=self.supplier,
            warehouse=self.warehouse,
            created_by=self.user,
            status='POSTED',
            currency='PHP',
            order_date=date(2026, 8, 5),
        )
        PurchaseOrderLine.objects.create(
            purchase_order=later_po,
            item=self.item2,
            unit=self.unit,
            qty_ordered=Decimal('5'),
            unit_price=Decimal('20.00'),
        )

        url = reverse('supplier_catalog_sync')
        response = self.client.post(url, {'selected_items': [str(self.item2.id)]}, follow=True)
        self.assertEqual(response.status_code, 200)

        entry2 = SupplierCatalogEntry.objects.get(supplier=self.supplier, item=self.item2)
        self.assertEqual(entry2.unit_price, Decimal('15.00'))
        self.assertEqual(entry2.last_po_number, grn.document_number)

    def test_full_inventory_resync_flags_pending_without_auto_syncing(self):
        # Running the "Full Inventory Resync" admin action must NOT silently
        # rewrite Supplier Catalog prices — it only flags that a sync is
        # suggested, so the operator can review the changes deliberately via
        # the "Sync Supplier Catalog" screen.
        import io
        from django.core.management import call_command
        from procurement.models import SupplierCatalogSyncState

        location = Location.objects.create(warehouse=self.warehouse, code='LOC-01', name='Main Location')
        GoodsReceiptLine.objects.create(
            goods_receipt=GoodsReceipt.objects.create(
                purchase_order=self.po,
                supplier=self.supplier,
                warehouse=self.warehouse,
                created_by=self.user,
                status='POSTED',
                receipt_date=date(2026, 8, 3),
            ),
            item=self.item1,
            location=location,
            qty=Decimal('10'),
            unit=self.unit,
        )

        state = SupplierCatalogSyncState.get_instance()
        self.assertFalse(state.sync_pending)

        buf = io.StringIO()
        call_command('resync_inventory', '--quiet', stdout=buf, stderr=buf)

        # No entries were created automatically — the sync is only suggested.
        self.assertEqual(SupplierCatalogEntry.objects.count(), 0)

        state.refresh_from_db()
        self.assertIsNotNone(state.last_resync_at)
        self.assertTrue(state.sync_pending)

    def test_syncing_catalog_clears_the_pending_resync_flag(self):
        from procurement.models import SupplierCatalogSyncState
        from django.utils import timezone

        state = SupplierCatalogSyncState.get_instance()
        state.last_resync_at = timezone.now()
        state.save(update_fields=['last_resync_at'])
        self.assertTrue(state.sync_pending)

        url = reverse('supplier_catalog_sync')
        response = self.client.post(url, {'selected_items': [str(self.item1.id)]}, follow=True)
        self.assertEqual(response.status_code, 200)

        state.refresh_from_db()
        self.assertFalse(state.sync_pending)

    def test_supplier_catalog_list_shows_pending_sync_banner(self):
        from procurement.models import SupplierCatalogSyncState
        from django.utils import timezone

        state = SupplierCatalogSyncState.get_instance()
        state.last_resync_at = timezone.now()
        state.save(update_fields=['last_resync_at'])

        response = self.client.get(reverse('supplier_catalog_list'))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['catalog_sync_pending'])
        self.assertContains(response, 'Sync Supplier Catalog Now')

        # No flag set — banner should not render.
        state.last_resync_at = None
        state.save(update_fields=['last_resync_at'])
        response = self.client.get(reverse('supplier_catalog_list'))
        self.assertFalse(response.context['catalog_sync_pending'])
        self.assertNotContains(response, 'Sync Supplier Catalog Now')
