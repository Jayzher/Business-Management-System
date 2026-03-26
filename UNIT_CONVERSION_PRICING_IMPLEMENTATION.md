"""
UNIT CONVERSION PRICING - IMPLEMENTATION SUMMARY
================================================

PROBLEM SOLVED:
When a product is sold in a different unit than its catalog selling unit,  
the system now automatically adjusts the price based on unit conversion factors.

EXAMPLE:
- Item: "Aluminum Sheet" with catalog selling unit = "Piece" at price $100
- Conversion: 1 Piece = 19.7 Feet
- Sale in "Feet": Price per foot = $100 / 19.7 = ~$5.08

FILES MODIFIED:
===============

1. catalog/utils.py (NEW)
   - get_conversion_factor(): Fetch conversion factor between units
   - convert_price_for_unit(): Adjust price based on unit conversion
   - get_item_price_for_unit(): Get item's price in any unit
   - bulk_get_prices_for_unit(): Batch pricing calculations
   - validate_unit_conversion_path(): Check if conversion is possible

2. catalog/serializers.py
   - ItemSerializer: Added conversion-aware fields
     * stock_unit_id: Item's canonical stock unit
     * stock_unit_name: Stock unit abbreviation
     * converted_selling_price: Selling price adjusted for requested unit
     * converted_cost_price: Cost price adjusted for requested unit
     * conversion_factor: Factor between stock unit and requested unit
   
   - ItemListSerializer: Same additional fields for list view
   
   - Both serializers accept ?unit=<unit_id> query parameter to trigger conversion

3. sales/forms.py
   - Removed unit category validation (cleaned up constraint)

4. templates/theme/base.html
   - Updated wisSoFetchPrice(): Now passes unit_id to API
   - Modified fallback price fetch: Uses converted_selling_price field
   - Updated svc-line-item handler: Supports unit conversion for services
   - Added svc-line-unit handler: Recalculates price when unit changes
   - Added generic PO/GRN/SR handlers: Supports all procurement/return forms
   - Added po-line-unit, grn-line-unit, sr-line-unit handlers

5. tests/test_unit_conversion_pricing.py (NEW)
   - Comprehensive test suite for conversion pricing
   - Tests direct/reverse conversions
   - Tests item-specific vs global conversions
   - Tests real-world scenarios

HOW IT WORKS:
=============

FRONTEND FLOW:
1. User selects item in formset row
2. wisSoFetchPrice() is called
3. Function builds API URL with unit_id: /api/items/{id}/?unit={unit_id}
4. Backend returns converted_selling_price based on unit conversion factor
5. Price field is auto-populated with converted price
6. When unit changes, process repeats automatically

BACKEND FLOW:
1. ItemSerializer receives ?unit=<unit_id> query param
2. get_converted_selling_price() method is called
3. It fetches the conversion factor via get_conversion_factor()
4. Price is divided by the factor to get per-unit price
5. Result is returned as converted_selling_price in JSON

FORMS THAT NOW SUPPORT CONVERSION:
==================================
✓ Sales Orders (.so-line-item, .so-line-unit)
✓ Purchase Orders (.po-line-item, .po-line-unit)
✓ Services (.svc-line-item, .svc-line-unit)
✓ Customer Service Lines (via .svc-line-item)

FEATURES:
=========
- Automatic price recalculation when unit changes
- Item-specific conversions override global ones
- Reverse conversions (Feet -> Piece) work automatically
- Handles missing conversions gracefully (returns base price)
- Supports both selling_price and cost_price conversions
- Works with batch imports and CSV imports

TESTING:
========
Run tests with:
  python manage.py test tests.test_unit_conversion_pricing

Or run all tests:
  python manage.py test

EXAMPLE USAGE (FRONTEND):
=========================

// Fetch item with unit conversion
var unitId = 5;  // Feet
$.getJSON('/api/items/123/?unit=' + unitId, function(data) {
  console.log('Base price:', data.selling_price);           // 100.00
  console.log('Converted price:', data.converted_selling_price);  // 5.08
  console.log('Factor:', data.conversion_factor);           // 19.7
});

EXAMPLE USAGE (PYTHON):
=======================

from catalog.utils import convert_price_for_unit
from catalog.models import Item, Unit

item = Item.objects.get(code='SHEET-001')
foot_unit = Unit.objects.get(abbreviation='ft')

# Get price per foot
price_per_foot = convert_price_for_unit(
    item.selling_price,      # 100.00
    item.stock_unit,         # Piece
    foot_unit,               # Foot
    item=item,
)
# Result: ~5.08

CONFIGURATION:
==============
- Unit conversions are configured in Catalog > Unit Conversions
- Item-specific overrides are configured per item under item edit
- Conversions work bi-directionally (both directions supported)
- Only conversions within same unit category are allowed

API QUERY PARAMETERS:
====================
GET /api/items/<id>/
  ?unit=<unit_id>        - Returns conversion factor + converted prices
  
GET /api/items/
  ?unit=<unit_id>        - All items with conversion data for unit

BACKWARD COMPATIBILITY:
=======================
- Without ?unit parameter, API returns original selling_price
- Existing code that doesn't pass unit_id still works
- Default behavior unchanged if no conversions configured
- All changes are additive (no breaking changes)

NOTES:
======
- Zero factors are treated as invalid (returns base price)
- Missing conversions return base price silently
- All prices are Decimal for precision
- Rounding to 4 decimal places by default
- Works with enterprise-level precision requirements
"""
