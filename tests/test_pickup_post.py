import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.test import TestCase
from django.urls import reverse


User = get_user_model()


class PickupPostViewTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        from catalog.models import Category, Item, ItemType, Unit, UnitCategory
        from inventory.models import StockBalance
        from partners.models import Customer
        from sales.models import SalesOrder, SalesOrderLine, SalesPickup, SalesPickupLine
        from warehouses.models import Warehouse, Location

        cls.user = User.objects.create_superuser('pickup_u', 'pickup@test.com', 'pass')
        cls.category = Category.objects.create(name='Pickup Cat', code='PICKCAT')
        cls.unit = Unit.objects.create(name='Piece', abbreviation='ppcs', category=UnitCategory.QUANTITY)
        cls.item = Item.objects.create(
            code='PICK-ITEM',
            name='Pickup Item',
            item_type=ItemType.FINISHED,
            category=cls.category,
            default_unit=cls.unit,
            cost_price=Decimal('10'),
            selling_price=Decimal('20'),
        )
        cls.warehouse = Warehouse.objects.create(name='Pickup Warehouse', code='PWH')
        cls.location = Location.objects.create(name='Pickup Location', code='PLOC', warehouse=cls.warehouse)
        cls.customer = Customer.objects.create(name='Pickup Customer', code='PCUST')
        cls.sales_order = SalesOrder.objects.create(
            document_number='SO-PICK-001',
            customer=cls.customer,
            warehouse=cls.warehouse,
            order_date=datetime.date.today(),
            created_by=cls.user,
        )
        SalesOrderLine.objects.create(
            sales_order=cls.sales_order,
            item=cls.item,
            qty_ordered=Decimal('2'),
            unit=cls.unit,
            unit_price=Decimal('20'),
        )
        cls.pickup = SalesPickup.objects.create(
            document_number='PU-TEST-001',
            sales_order=cls.sales_order,
            customer=cls.customer,
            warehouse=cls.warehouse,
            pickup_date=datetime.date.today(),
            created_by=cls.user,
        )
        SalesPickupLine.objects.create(
            pickup=cls.pickup,
            item=cls.item,
            location=cls.location,
            qty=Decimal('2'),
            unit=cls.unit,
        )
        StockBalance.objects.create(
            item=cls.item,
            location=cls.location,
            qty_on_hand=Decimal('10'),
            qty_reserved=Decimal('0'),
        )

    def test_pickup_post_view_redirects_and_posts_pickup(self):
        from core.models import Invoice, DocumentStatus

        self.client.force_login(self.user)

        response = self.client.post(reverse('pickup_post', args=[self.pickup.pk]), follow=True)

        self.assertEqual(response.status_code, 200)
        self.pickup.refresh_from_db()
        self.assertEqual(self.pickup.status, DocumentStatus.POSTED)
        self.assertTrue(Invoice.objects.filter(sales_order=self.sales_order, is_void=False).exists())

        messages = [m.message for m in get_messages(response.wsgi_request)]
        self.assertTrue(any('posted' in message.lower() for message in messages))
