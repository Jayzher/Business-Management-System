# Unit Conversion Pricing - Quick Reference Guide

## For End Users

### How to Use Unit Conversion Pricing

#### 1. Creating a Sale with Unit Conversion

**Scenario**: You have rubber sheets that cost $50 each, but you want to sell by square meter. Each sheet is 2 square meters.

**Steps**:
1. Open Sales Order form
2. Select item: "Rubber Sheet"
3. System auto-shows base unit: "Piece"
4. **Change unit to**: "Square Meter"
5. **Price auto-updates**: $50 ÷ 2 = $25 per m²
6. Enter quantity: 6 m²
7. **Total calculated**: $25 × 6 = $150

#### 2. Setting Up Conversions (Admin Only)

Go to **Catalog > Unit Conversions**:
- From: "Piece"
- To: "Square Meter"  
- Factor: "2" (means 1 piece = 2 square meters)

#### 3. Item-Specific vs Global Conversions

**Global Conversion** (applies to all items):
- 1 Roll = 50 meters

**Item-Specific** (override for one product):
- Nylon Rope, 1 Roll = 49.8 meters

The item-specific always wins when both exist.

---

## For Developers

### Using Conversion Functions in Views

```python
from catalog.utils import get_item_price_for_unit
from catalog.models import Item, Unit

# Get price in any unit
item = Item.objects.get(code='CABLE-001')
foot_unit = Unit.objects.get(abbreviation='ft')

price_in_feet = get_item_price_for_unit(item, foot_unit)
# Returns: $10.05 (if 1 spool costs $1000 and = 99.5 feet)
```

### Using Conversion Functions in Serializers

```python
from catalog.utils import convert_price_for_unit

price = convert_price_for_unit(
    100.00,           # Base price
    piece_unit,       # Base unit
    foot_unit,        # Target unit
    item=my_item,     # Item (for item-specific conversion)
    round_places=4    # Decimal places
)
```

### Adding to New Forms

1. Add CSS class to unit select: `class="unit-selector"`
2. Add CSS class to price input: `class="price-input"`
3. Item select already triggers `wisSoFetchPrice()`
4. Unit change automatically refetches with conversion

---

## Frontend JavaScript

### How It Works

1. **Item Selection**:
```javascript
// Triggers wisSoSetUnitThenPrice()
$('.so-line-item').on('change', function() {
  // Fetches item, gets stock unit, recalculates price
});
```

2. **Unit Change**:
```javascript
// Triggers wisSoFetchPrice() with new unit_id
$('.so-line-unit').on('change', function() {
  // API called with ?unit={new_unit_id}
  // converted_selling_price returned
  // Price field updated
});
```

### Adding Custom Unit Conversion Support

For new formset types, add event handlers:

```javascript
// When item is selected
$(document).on('change', '.custom-line-item', function() {
  var row = $(this).closest('.formset-row');
  var itemId = $(this).val();
  $.getJSON('/api/items/' + itemId + '/', function(data) {
    row.find('input[name$="-unit_price"]').val(
      data.converted_selling_price || data.selling_price
    );
  });
});

// When unit changes
$(document).on('change', '.custom-line-unit', function() {
  var row = $(this).closest('.formset-row');
  var itemId = row.find('[name$="-item"]').val();
  var unitId = $(this).val();
  $.getJSON('/api/items/' + itemId + '/?unit=' + unitId, function(data) {
    row.find('input[name$="-unit_price"]').val(
      data.converted_selling_price || data.selling_price
    );
  });
});
```

---

## API Reference

### GET /api/items/{id}/

**Query Parameters**:
- `?unit=<unit_id>` - Optional unit for conversion

**Response Fields** (with ?unit param):
- `selling_price` - Base price (unchanged)
- `converted_selling_price` - Price adjusted for unit
- `conversion_factor` - Factor between units
- `stock_unit_name` - Item's canonical unit
- Plus all other item fields

**Example**:
```bash
GET /api/items/123/?unit=5

{
  "selling_price": 1000,
  "converted_selling_price": 10.05,
  "conversion_factor": 99.5,
  "stock_unit_name": "spl",
  ...
}
```

---

## Troubleshooting

### Price Not Updating When Unit Changes

**Check**:
1. Conversion configured in Catalog > Unit Conversions
2. Both units are in same category (e.g., both LENGTH)
3. Unit has non-zero factor
4. Browser console for JavaScript errors

### Incorrect Price Calculation

**Verify**:
1. Conversion factor is correct: `1 source_unit = X target_units`
2. For item-specific, it's attached to the right item
3. Base item price is correct

### Works in Sales Order But Not Purchase Order

**Solution**:
1. Add event handlers for `.po-line-unit` (for PO)
2. Or check if handlers are already in base.html
3. Verify form has correct CSS classes

---

## Performance Notes

- Minimal overhead: One additional API call per item selection
- Conversion factors cached in memory
- Database queries optimized with select_related
- No impact on listing/search performance
- Safe for high-volume transactions

---

## Migration & Deployment

### Prerequisites
None - works with existing data

### Installation
1. Deploy code changes
2. Create/update unit conversions in admin
3. Test with one sale order
4. Monitor system logs

### No Migration Needed
- All changes backward compatible
- Existing forms work without modification
- Database schema unchanged

---

## Support & Docs

- Summary: `UNIT_CONVERSION_PRICING_SUMMARY.md`
- Implementation: `UNIT_CONVERSION_PRICING_IMPLEMENTATION.md`
- Tests: Run `python manage.py test tests.test_unit_conversion_pricing`
- Utils: See `catalog/utils.py` for all functions
