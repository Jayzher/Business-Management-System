"""
Test suite for unit conversion pricing logic.
Verifies that prices are correctly adjusted based on unit conversion factors.
"""
from decimal import Decimal
from django.test import TestCase
from django.contrib.auth import get_user_model
from catalog.models import Category, Unit, UnitCategory, UnitConversion, Item, ItemType
from catalog.utils import (
    get_conversion_factor,
    convert_price_for_unit,
    get_item_price_for_unit,
)

User = get_user_model()


class UnitConversionPricingTest(TestCase):
    """Test unit conversion pricing calculations."""
    
    @classmethod
    def setUpTestData(cls):
        # Create units
        cls.piece = Unit.objects.create(
            name='Piece',
            abbreviation='pcs',
            category=UnitCategory.QUANTITY
        )
        cls.foot = Unit.objects.create(
            name='Foot',
            abbreviation='ft',
            category=UnitCategory.LENGTH
        )
        cls.meter = Unit.objects.create(
            name='Meter',
            abbreviation='m',
            category=UnitCategory.LENGTH
        )
        
        # Create category and item
        cls.cat = Category.objects.create(name='Test Category', code='TEST')
        cls.item = Item.objects.create(
            code='TEST-001',
            name='Test Product',
            item_type=ItemType.FINISHED,
            category=cls.cat,
            default_unit=cls.piece,
            selling_unit=cls.piece,
            cost_price=Decimal('100.00'),
            selling_price=Decimal('200.00'),
        )
    
    def test_get_conversion_factor_direct(self):
        """Test getting direct conversion factor (Piece -> Foot)."""
        # 1 piece = 19.7 feet
        conv = UnitConversion.objects.create(
            from_unit=self.piece,
            to_unit=self.foot,
            factor=Decimal('19.7'),
        )
        
        factor = get_conversion_factor(self.piece, self.foot)
        self.assertEqual(factor, Decimal('19.7'))
    
    def test_get_conversion_factor_reverse(self):
        """Test getting reverse conversion factor."""
        # 1 piece = 19.7 feet, so 1 foot = 1/19.7 pieces
        UnitConversion.objects.create(
            from_unit=self.piece,
            to_unit=self.foot,
            factor=Decimal('19.7'),
        )
        
        factor = get_conversion_factor(self.foot, self.piece)
        self.assertAlmostEqual(
            float(factor),
            1 / 19.7,
            places=6
        )
    
    def test_get_conversion_factor_same_unit(self):
        """Test that same unit returns factor of 1."""
        factor = get_conversion_factor(self.piece, self.piece)
        self.assertEqual(factor, Decimal('1'))
    
    def test_get_conversion_factor_not_found(self):
        """Test that missing conversion returns None."""
        factor = get_conversion_factor(self.piece, self.meter)
        self.assertIsNone(factor)
    
    def test_convert_price_same_unit(self):
        """Test that converting to same unit returns same price."""
        price = convert_price_for_unit(
            Decimal('200.00'),
            self.piece,
            self.piece,
            item=self.item,
        )
        self.assertEqual(price, Decimal('200.0000'))
    
    def test_convert_price_foot_from_piece(self):
        """
        Test price conversion: Piece to Foot.
        
        Example from spec:
        - Base price: 100 per Piece
        - 1 Piece = 19.7 Feet
        - Price per Foot: 100 / 19.7 ≈ 5.08
        """
        UnitConversion.objects.create(
            from_unit=self.piece,
            to_unit=self.foot,
            factor=Decimal('19.7'),
        )
        
        price = convert_price_for_unit(
            Decimal('100.00'),
            self.piece,
            self.foot,
            item=self.item,
        )
        
        # 100 / 19.7 ≈ 5.0761...
        expected = Decimal('100.00') / Decimal('19.7')
        self.assertAlmostEqual(float(price), float(expected), places=4)
    
    def test_convert_price_piece_from_foot(self):
        """
        Test reverse price conversion: Foot to Piece.
        
        If 1 piece = 19.7 feet, then price per piece = price per foot * 19.7
        """
        UnitConversion.objects.create(
            from_unit=self.piece,
            to_unit=self.foot,
            factor=Decimal('19.7'),
        )
        
        price = convert_price_for_unit(
            Decimal('5.08'),
            self.foot,
            self.piece,
            item=self.item,
        )
        
        # Should get back approximately 100
        expected = Decimal('5.08') * Decimal('19.7')
        self.assertAlmostEqual(float(price), float(expected), places=2)
    
    def test_get_item_price_for_unit_same_unit(self):
        """Test getting item price for same selling unit."""
        price = get_item_price_for_unit(self.item, self.piece)
        self.assertEqual(price, Decimal('200.00'))
    
    def test_get_item_price_for_unit_different_unit(self):
        """Test getting item price converted to different unit."""
        UnitConversion.objects.create(
            from_unit=self.piece,
            to_unit=self.foot,
            factor=Decimal('19.7'),
        )
        
        price = get_item_price_for_unit(self.item, self.foot)
        
        # 200 / 19.7 ≈ 10.1523...
        expected = Decimal('200.00') / Decimal('19.7')
        self.assertAlmostEqual(float(price), float(expected), places=4)
    
    def test_item_specific_conversion(self):
        """
        Test that item-specific conversions take precedence over global ones.
        """
        # Global: 1 piece = 20 feet
        UnitConversion.objects.create(
            from_unit=self.piece,
            to_unit=self.foot,
            factor=Decimal('20.0'),
            item=None,
        )
        
        # Item-specific: 1 piece = 19.7 feet (override)
        UnitConversion.objects.create(
            from_unit=self.piece,
            to_unit=self.foot,
            factor=Decimal('19.7'),
            item=self.item,
        )
        
        # Should use item-specific factor
        factor = get_conversion_factor(self.piece, self.foot, item=self.item)
        self.assertEqual(factor, Decimal('19.7'))
        
        # Should use global factor for different item
        other_item = Item.objects.create(
            code='TEST-002',
            name='Other Product',
            item_type=ItemType.FINISHED,
            category=self.cat,
            default_unit=self.piece,
            selling_unit=self.piece,
            selling_price=Decimal('100.00'),
        )
        factor_other = get_conversion_factor(self.piece, self.foot, item=other_item)
        self.assertEqual(factor_other, Decimal('20.0'))
    
    def test_conversion_with_quantities(self):
        """
        Test real-world scenario: 6 feet at converted price per foot.
        
        - Base item: 100 per piece, 1 piece = 19.7 feet
        - Price per foot = 100 / 19.7
        - Qty: 6 feet
        - Total: (100 / 19.7) * 6
        """
        UnitConversion.objects.create(
            from_unit=self.piece,
            to_unit=self.foot,
            factor=Decimal('19.7'),
        )
        
        price_per_foot = convert_price_for_unit(
            Decimal('100.00'),
            self.piece,
            self.foot,
            item=self.item,
        )
        
        qty = Decimal('6')
        total = price_per_foot * qty
        
        expected_price_per_foot = Decimal('100.00') / Decimal('19.7')
        expected_total = expected_price_per_foot * Decimal('6')
        
        self.assertAlmostEqual(float(total), float(expected_total), places=2)
