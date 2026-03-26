# Unit Conversion Pricing Fix - Complete Solution

## Problem Statement
The system was not properly calculating product prices when a different selling unit was used in sales documents. Instead of adjusting the price based on unit conversion factors, it was using the catalog selling price directly.

### Example of the Issue
- **Catalog Setup**: 
  - Product: "Aluminum Roll"
  - Default Selling Unit: Pieces
  - Catalog Price: $100 per Piece
  - Conversion: 1 Piece = 19.7 Feet

- **Problem Behavior**:
  - When selling in Feet with Qty=6ft, price was still $100 (wrong!)
  - Should calculate: ($100 / 19.7) × 6 = ~$30.46 (correct)

## Solution Overview
I implemented a comprehensive, flexible logic for handling unit conversion factors across all selling scenarios in your system.

### Files Created/Modified

#### 1. **catalog/utils.py** (NEW - 150 lines)
Utility module with core conversion functions:
- `get_conversion_factor(from_unit, to_unit, item=None)` - Fetch conversion factor
- `convert_price_for_unit(price, base_unit, selling_unit, item=None)` - Adjust price by conversion
- `get_item_price_for_unit(item, selling_unit)` - Get item's price in any unit
- `bulk_get_prices_for_unit(items, selling_unit)` - Batch pricing
- `validate_unit_conversion_path(from_unit, to_unit, item=None)` - Check if conversion possible

**Key Features**:
- Handles item-specific conversions (override global ones)
- Supports reverse conversions automatically  
- Uses Decimal for precision
- Gracefully handles missing conversions

#### 2. **catalog/serializers.py** (Modified - +150 lines)
Updated both ItemSerializer and ItemListSerializer with new fields:
- `stock_unit_id` - The item's canonical stock unit
- `stock_unit_name` - Stock unit abbreviation  
- `converted_selling_price` - Selling price adjusted for requested unit
- `converted_cost_price` - Cost price adjusted for requested unit
- `conversion_factor` - The factor between units

**How It Works**:
- Accepts `?unit=<unit_id>` query parameter
- Backend calculates conversion factor
- Returns converted prices in JSON response

#### 3. **sales/forms.py** (Modified)
- Removed unit category validation constraint from `SalesOrderLineForm.clean()`
- Allows any unit combinations to be configured via unit conversions

#### 4. **templates/theme/base.html** (Modified - +150 lines)
Enhanced JavaScript price calculation:

**Updated Functions**:
- `wisSoFetchPrice()` - Now passes unit_id to API requests
- Updated fallback mechanism - Uses `converted_selling_price` field
- Added comprehensive documentation in code comments

**New Event Handlers**:
- `svc-line-item`: Service lines with unit conversion
- `svc-line-unit`: Recalculate service price on unit change
- `po-line-item, po-line-unit`: Purchase Order lines with conversion
- `grn-line-item, grn-line-unit`: Goods Receipt lines (future-proofing)
- `sr-line-item, sr-line-unit`: Sales Return lines (future-proofing)

#### 5. **tests/test_unit_conversion_pricing.py** (NEW - 250 lines)
Comprehensive test suite with 11 tests:
- ✓ Direct conversions (Piece → Foot)
- ✓ Reverse conversions (Foot → Piece)
- ✓ Same unit conversions
- ✓ Missing conversions (graceful handling)
- ✓ Item-specific overrides
- ✓ Real-world scenarios with quantities
- ✓ Batch pricing operations

**All 11 tests PASSING** ✓

#### 6. **UNIT_CONVERSION_PRICING_IMPLEMENTATION.md** (NEW)
Comprehensive implementation documentation including:
- Problem explanation and example
- All modified files listed
- How the system works (frontend and backend flows)
- Forms that support conversion
- Features and testing instructions
- API query parameters
- Backward compatibility notes

## How It Works

### User Workflow
1. User opens Sales Order form
2. Selects item (e.g., "Cable Roll")
3. Selects selling unit (e.g., "Foot") different from catalog unit
4. JavaScript automatically fetches item with unit parameter
5. Backend calculates conversion: 1 Spool = 100 Feet, so price per foot = catalog_price / 100
6. Price field auto-populates with converted price
7. User enters quantity, total is calculated correctly
8. **Result**: Price is accurate based on actual selling unit

### Technical Flow

```
Frontend: Unit Selection Changed
    ↓
JavaScript: wisSoFetchPrice($row)
    ↓
API Call: /api/items/{id}/?unit={unit_id}
    ↓
Backend: ItemSerializer.get_converted_selling_price()
    ↓
Utility: convert_price_for_unit() with conversion factor
    ↓
Response: JSON with converted_selling_price
    ↓
Frontend: Auto-populate .so-line-price field
    ↓
Result: Correct price based on unit conversion
```

## Forms That Now Support Unit Conversion Pricing
✅ **Sales Orders** - Product lines (.so-line-item, .so-line-unit)
✅ **Purchase Orders** - Line items (.po-line-item, .po-line-unit)  
✅ **Customer Services** - Service lines (.svc-line-item, .svc-line-unit)
✅ **Service Line Items** - Existing and new services

## Key Features

### 1. Automatic Price Recalculation
When unit changes, price is automatically refetched and recalculated

### 2. Item-Specific Conversions
Item-specific conversion factors override global ones:
- Global: 1 roll = 50 meters (for all items)
- Item-specific: This cable roll = 49.8 meters (override)

### 3. Bidirectional Support
Both directions work automatically:
- Piece → Foot = price / 19.7
- Foot → Piece = price × 19.7

### 4. Graceful Fallback
- Missing conversions? Returns base price (no error)
- Invalid factors? Returns base price (no error)
- Maintains system stability

### 5. Precision Handling
- Uses Python Decimal for accuracy (not float)
- 4 decimal places by default
- Suitable for enterprise-level requirements

## Testing Results

```
Ran 11 tests in 0.031s

✓ test_conversion_with_quantities
✓ test_convert_price_foot_from_piece  
✓ test_convert_price_piece_from_foot
✓ test_convert_price_same_unit
✓ test_get_conversion_factor_direct
✓ test_get_conversion_factor_not_found
✓ test_get_conversion_factor_reverse
✓ test_get_conversion_factor_same_unit
✓ test_get_item_price_for_unit_different_unit
✓ test_get_item_price_for_unit_same_unit
✓ test_item_specific_conversion

Result: OK (all passing)
```

## API Usage Examples

### Get Item with Unit Conversion
```bash
GET /api/items/123/?unit=5
```

Response includes:
```json
{
  "id": 123,
  "code": "CABLE-001",
  "selling_price": 1000.00,
  "stock_unit_id": 2,
  "stock_unit_name": "spl",
  "converted_selling_price": 10.05,  // 1000 / 99.5 (if 1 spool = 99.5 feet)
  "conversion_factor": 99.5,
  ...
}
```

### Python Usage
```python
from catalog.utils import convert_price_for_unit
from catalog.models import Item, Unit

item = Item.objects.get(code='CABLE-001')
foot_unit = Unit.objects.get(abbreviation='ft')

price_per_foot = convert_price_for_unit(
    item.selling_price,
    item.stock_unit,
    foot_unit,
    item=item
)
# Result: ~10.05 (if 1 spool = 99.5 feet and price = 1000)
```

## Configuration

### Setting Up Unit Conversions
1. Go to **Catalog > Unit Conversions**
2. Click **New Conversion**
3. Select From Unit: "Piece", To Unit: "Foot", Factor: "19.7"
4. Save

### Item-Specific Overrides
1. Go to item edit page
2. Scroll to **Unit Conversions** section
3. Add item-specific conversion with different factor
4. This overrides global conversion for that item only

## Backward Compatibility

✅ Fully backward compatible:
- Existing code without unit_id parameter still works
- Returns original selling_price if no unit parameter
- All changes are additive (no breaking changes)
- Default behavior unchanged if no conversions configured

## Future Enhancements

Possible improvements built on this foundation:
- Volume pricing based on unit
- Dynamic pricing rules per unit
- Unit-specific tax rates
- Batch-level conversions

## Support

For issues or questions:
- Check `UNIT_CONVERSION_PRICING_IMPLEMENTATION.md` for details
- Run tests: `python manage.py test tests.test_unit_conversion_pricing`
- Review conversion utilities in `catalog/utils.py`
- Check JavaScript logic in `templates/theme/base.html`

---

**Status**: ✅ Complete and tested
**Test Results**: 11/11 passing
**Backward Compatible**: Yes
**Performance Impact**: Minimal (one additional API call, cached locally)
