"""
Test COGS calculations with unit conversions applied.

Ensures that COGS is properly adjusted when items are sold in different units
than their stock unit, using the conversion factors.
"""
from decimal import Decimal
from django.test import TestCase
from catalog.models import Item, Unit, UnitConversion, Category
from sales.models import SalesOrder, SalesOrderLine
from pos.models import POSSale, POSSaleLine
from services.models import CustomerService, ServiceLine
from accounts.models import User
from warehouses.models import Warehouse, Location
from core.cogs import pos_sale_cogs, sales_order_cogs, service_invoice_cogs


class COGSWithUnitConversionTestCase(TestCase):
    """Test COGS calculations with unit conversions."""
    
    def setUp(self):
        """Set up test data with unit conversions."""
        # Create category
        self.category = Category.objects.create(
            name='Test Category',
            code='TEST'
        )
        
        # Create units
        self.unit_piece = Unit.objects.create(
            name='Piece',
            abbreviation='pc',
            is_active=True
        )
        self.unit_foot = Unit.objects.create(
            name='Foot',
            abbreviation='ft',
            is_active=True
        )
        self.unit_meter = Unit.objects.create(
            name='Meter',
            abbreviation='m',
            is_active=True
        )
        
        # Create unit conversions
        # 1 Piece = 19.7 Feet
        UnitConversion.objects.create(
            from_unit=self.unit_piece,
            to_unit=self.unit_foot,
            factor=Decimal('19.7'),
            is_active=True
        )
        
        # 1 Meter = 3.28084 Feet
        UnitConversion.objects.create(
            from_unit=self.unit_meter,
            to_unit=self.unit_foot,
            factor=Decimal('3.28084'),
            is_active=True
        )
        
        # Create item with default_unit = Piece, selling_unit = Piece
        self.item = Item.objects.create(
            code='TEST-001',
            name='Test Product',
            category=self.category,
            default_unit=self.unit_piece,
            selling_unit=self.unit_piece,
            cost_price=Decimal('100.00'),
            selling_price=Decimal('150.00'),
            is_active=True
        )
        
        # Create warehouse and user
        self.warehouse = Warehouse.objects.create(
            code='WH1',
            name='Warehouse 1',
            is_active=True
        )
        
        # Create warehouse location
        self.location = Location.objects.create(
            warehouse=self.warehouse,
            code='LOC-1',
            name='Location 1',
            location_type='SHELF',
            is_active=True
        )
        
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
    
    def test_cogs_same_unit(self):
        """Test COGS when selling in the same unit as stock unit."""
        # Cost price = $100/pc, qty = 6 pc
        # Expected COGS = $100 * 6 = $600
        
        pos_sale = POSSale.objects.create(
            warehouse=self.warehouse,
            location=self.location,
            created_by=self.user
        )
        POSSaleLine.objects.create(
            sale=pos_sale,
            item=self.item,
            qty=Decimal('6'),
            unit=self.unit_piece,
            unit_price=Decimal('150.00')
        )
        
        cogs = pos_sale_cogs(pos_sale)
        expected = Decimal('600.00')  # 100 * 6
        
        self.assertEqual(cogs, expected)
    
    def test_cogs_different_unit_foot_from_piece(self):
        """Test COGS when selling in Feet instead of Pieces.
        
        Cost price = $100/pc
        1 pc = 19.7 ft
        Cost per foot = $100 / 19.7 ≈ $5.076
        Qty sold = 6 ft
        Expected COGS = $5.076 * 6 ≈ $30.46
        """
        pos_sale = POSSale.objects.create(
            warehouse=self.warehouse,
            location=self.location,
            created_by=self.user
        )
        POSSaleLine.objects.create(
            sale=pos_sale,
            item=self.item,
            qty=Decimal('6'),
            unit=self.unit_foot,
            unit_price=Decimal('5.0760')
        )
        
        cogs = pos_sale_cogs(pos_sale)
        
        # $100 / 19.7 * 6 = $30.4567...
        expected = Decimal('100.00') / Decimal('19.7') * Decimal('6')
        expected = expected.quantize(Decimal('0.01'))
        
        self.assertEqual(cogs, expected)
    
    def test_cogs_different_unit_meter_from_piece(self):
        """Test COGS when selling in Meters instead of Pieces.
        
        Cost price = $100/pc
        1 pc = 19.7 ft = 6.0096 m (19.7 / 3.28084)
        Cost per meter = $100 / 6.0096 ≈ $16.64
        Qty sold = 10 m
        Expected COGS = $16.64 * 10 = $166.40
        """
        pos_sale = POSSale.objects.create(
            warehouse=self.warehouse,
            location=self.location,
            created_by=self.user
        )
        POSSaleLine.objects.create(
            sale=pos_sale,
            item=self.item,
            qty=Decimal('10'),
            unit=self.unit_meter,
            unit_price=Decimal('16.6396')
        )
        
        cogs = pos_sale_cogs(pos_sale)
        
        # Conversion: 1 pc = 19.7 ft, 1 m = 3.28084 ft
        # 1 pc = 19.7 / 3.28084 meters
        # Cost per meter = 100 / (19.7 / 3.28084) = 100 * 3.28084 / 19.7
        unit_feet_per_pc = Decimal('19.7')
        unit_feet_per_m = Decimal('3.28084')
        cost_per_meter = Decimal('100') * unit_feet_per_m / unit_feet_per_pc
        expected = cost_per_meter * Decimal('10')
        expected = expected.quantize(Decimal('0.01'))
        
        self.assertEqual(cogs, expected)
    
    def test_sales_order_cogs_with_unit_conversion(self):
        """Test sales order COGS calculation with unit conversions."""
        # Create customer
        from accounts.models import Customer
        customer = Customer.objects.create(
            name='Test Customer',
            customer_type='RETAIL'
        )
        
        # Create sales order with 2 lines in different units
        so = SalesOrder.objects.create(
            customer=customer,
            warehouse=self.warehouse,
            created_by=self.user,
            order_date='2024-01-01'
        )
        
        # Line 1: 6 pieces @ conversion
        line1 = SalesOrderLine.objects.create(
            order=so,
            item=self.item,
            qty_ordered=Decimal('6'),
            unit=self.unit_piece,
            unit_price=Decimal('150.00')
        )
        
        # Line 2: 10 feet @ conversion
        line2 = SalesOrderLine.objects.create(
            order=so,
            item=self.item,
            qty_ordered=Decimal('10'),
            unit=self.unit_foot,
            unit_price=Decimal('5.0760')
        )
        
        cogs = sales_order_cogs(so)
        
        # Line 1: $100 * 6 = $600
        line1_cogs = Decimal('100.00') * Decimal('6')
        
        # Line 2: ($100 / 19.7) * 10 = $50.76
        line2_cogs = (Decimal('100.00') / Decimal('19.7')) * Decimal('10')
        
        expected = (line1_cogs + line2_cogs).quantize(Decimal('0.01'))
        
        self.assertEqual(cogs, expected)
    
    def test_service_cogs_with_unit_conversion(self):
        """Test service invoice COGS calculation with unit conversions."""
        # Create customer
        from accounts.models import Customer
        customer = Customer.objects.create(
            name='Service Customer',
            customer_type='RETAIL'
        )
        
        # Create customer service
        service = CustomerService.objects.create(
            customer=customer,
            warehouse=self.warehouse,
            created_by=self.user,
            service_date='2024-01-01'
        )
        
        # Add service lines in different units
        ServiceLine.objects.create(
            service=service,
            item=self.item,
            qty=Decimal('8'),
            unit=self.unit_foot,
            unit_price=Decimal('5.0760')
        )
        
        # Create invoice
        from core.models import Invoice
        invoice = Invoice.objects.create(
            customer=customer,
            created_by=self.user
        )
        invoice.customer_services.add(service)
        
        cogs = service_invoice_cogs(invoice)
        
        # COGS: ($100 / 19.7) * 8
        expected = (Decimal('100.00') / Decimal('19.7')) * Decimal('8')
        expected = expected.quantize(Decimal('0.01'))
        
        self.assertEqual(cogs, expected)
    
    def test_cogs_multiple_items_mixed_units(self):
        """Test COGS with multiple items each in different units."""
        # Create second item
        item2 = Item.objects.create(
            code='TEST-002',
            name='Test Product 2',
            category=self.category,
            default_unit=self.unit_meter,
            selling_unit=self.unit_meter,
            cost_price=Decimal('50.00'),
            selling_price=Decimal('75.00'),
            is_active=True
        )
        
        # Create POS sale with mixed items and units
        pos_sale = POSSale.objects.create(
            warehouse=self.warehouse,
            location=self.location,
            created_by=self.user
        )
        
        # Item 1: 5 pieces
        POSSaleLine.objects.create(
            sale=pos_sale,
            item=self.item,
            qty=Decimal('5'),
            unit=self.unit_piece,
            unit_price=Decimal('150.00')
        )
        
        # Item 2: 3 feet (converted from meters)
        POSSaleLine.objects.create(
            sale=pos_sale,
            item=item2,
            qty=Decimal('3'),
            unit=self.unit_foot,
            unit_price=Decimal('15.2532')  # 50 / 3.28084 * 1
        )
        
        cogs = pos_sale_cogs(pos_sale)
        
        # Item 1 COGS: $100 * 5 = $500
        item1_cogs = Decimal('100.00') * Decimal('5')
        
        # Item 2 COGS: ($50 / 3.28084) * 3
        item2_cogs = (Decimal('50.00') / Decimal('3.28084')) * Decimal('3')
        
        expected = (item1_cogs + item2_cogs).quantize(Decimal('0.01'))
        
        self.assertEqual(cogs, expected)
    
    def test_cogs_zero_quantity(self):
        """Test COGS with zero quantity."""
        pos_sale = POSSale.objects.create(
            warehouse=self.warehouse,
            location=self.location,
            created_by=self.user
        )
        POSSaleLine.objects.create(
            sale=pos_sale,
            item=self.item,
            qty=Decimal('0'),
            unit=self.unit_piece,
            unit_price=Decimal('150.00')
        )
        
        cogs = pos_sale_cogs(pos_sale)
        expected = Decimal('0.00')
        
        self.assertEqual(cogs, expected)
    
    def test_cogs_negative_cost_price(self):
        """Test COGS with zero or negative cost price (edge case)."""
        # Create item with zero cost price
        free_item = Item.objects.create(
            code='FREE-001',
            name='Free Item',
            category=self.category,
            default_unit=self.unit_piece,
            selling_unit=self.unit_piece,
            cost_price=Decimal('0.00'),
            selling_price=Decimal('10.00'),
            is_active=True
        )
        
        pos_sale = POSSale.objects.create(
            warehouse=self.warehouse,
            location=self.location,
            created_by=self.user
        )
        POSSaleLine.objects.create(
            sale=pos_sale,
            item=free_item,
            qty=Decimal('10'),
            unit=self.unit_piece,
            unit_price=Decimal('10.00')
        )
        
        cogs = pos_sale_cogs(pos_sale)
        expected = Decimal('0.00')
        
        self.assertEqual(cogs, expected)
