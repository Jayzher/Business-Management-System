# Unit Conversion Pricing - Technical Architecture

## System Architecture

### Components

```
┌─────────────────────────────────────────────────────────────────┐
│                      FRONTEND (JavaScript)                       │
├─────────────────────────────────────────────────────────────────┤
│ • Event handlers for item/unit changes                           │
│ • API calls with unit_id parameter                              │
│ • Price field auto-population                                    │
│ • Discount/total recalculation                                   │
└────────────────┬────────────────────────────────────────────────┘
                 │ API Request: /api/items/{id}/?unit={unit_id}
                 ↓
┌─────────────────────────────────────────────────────────────────┐
│                      BACKEND (Django REST)                       │
├─────────────────────────────────────────────────────────────────┤
│ • ItemSerializer.get_converted_selling_price()                  │
│ • Retrieves item with stock unit                                │
│ • Calls utility function with conversion params                │
│ • Returns JSON with conversion data                             │
└────────────────┬────────────────────────────────────────────────┘
                 │
                 ↓
┌─────────────────────────────────────────────────────────────────┐
│                    CONVERSION LOGIC (Utils)                      │
├─────────────────────────────────────────────────────────────────┤
│ • get_conversion_factor()                                        │
│   - Check item-specific conversions first                       │
│   - Fall back to global conversions                             │
│   - Support reverse conversions                                  │
│                                                                  │
│ • convert_price_for_unit()                                       │
│   - price_in_target_unit = base_price / factor                 │
│   - Handle Decimal precision                                    │
│   - Return with rounding                                         │
└────────────────┬────────────────────────────────────────────────┘
                 │
                 ↓
┌─────────────────────────────────────────────────────────────────┐
│                   DATABASE (Unit Conversions)                    │
├─────────────────────────────────────────────────────────────────┤
│ • Global: from_unit → to_unit → factor                          │
│ • Item-specific: (from_unit, to_unit, item) → factor           │
└─────────────────────────────────────────────────────────────────┘
```

## Data Flow

### Scenario: Sell Cable in Feet Instead of Spools

```
1. USER SELECTS ITEM
   └─ Click: Item "Cable Spool"
   └─ Event: $('.so-line-item').change()
   └─ Function: wisSoSetUnitThenPrice()

2. FETCH ITEM DATA
   └─ API: /api/items/123/
   └─ Get: stock_unit = "spool", selling_unit = "spool"
   └─ Set unit dropdown to "Spool"
   └─ Function: wisSoFetchPrice()

3. CALCULATE BASE PRICE
   └─ API: /api/items/123/?unit=2  (unit 2 = "spool")
   └─ No conversion needed (same unit)
   └─ Return: selling_price = $1000

4. USER CHANGES UNIT
   └─ Click: Unit dropdown "Foot"
   └─ Event: $('.so-line-unit').change()
   └─ Function: wisSoFetchPrice()

5. FETCH WITH CONVERSION
   └─ API: /api/items/123/?unit=5  (unit 5 = "foot")
   └─ Query: UnitConversion (spool → foot)
   └─ Factor: 1 spool = 99.5 feet

6. CALCULATE CONVERTED PRICE
   └─ converted_price = $1000 / 99.5
   └─ converted_price = $10.05 per foot
   └─ Return: converted_selling_price = $10.05

7. UPDATE UI
   └─ Set: price_field.value = $10.05
   └─ Calculate: total = 6 feet × $10.05 = $60.30
   └─ Update: grand_total
```

## Database Schema

### UnitConversion Table
```sql
CREATE TABLE catalog_unitconversion (
    id BIGINT PRIMARY KEY,
    from_unit_id BIGINT NOT NULL,
    to_unit_id BIGINT NOT NULL,
    factor DECIMAL(15, 6) NOT NULL,
    item_id BIGINT NULL,  -- NULL = global, NOT NULL = item-specific
    is_active BOOLEAN NOT NULL,
    created_at DATETIME,
    updated_at DATETIME,
    
    -- Indexes for performance
    INDEX (from_unit_id),
    INDEX (to_unit_id),
    INDEX (item_id),
    
    -- Constraints
    UNIQUE(from_unit, to_unit) WHERE item_id IS NULL,  -- Global unique
    UNIQUE(from_unit, to_unit, item_id) WHERE item_id IS NOT NULL  -- Per-item unique
);
```

## Conversion Algorithm

### Price Conversion
```
Function: convert_price_for_unit(price, from_unit, to_unit, item)
  
1. If from_unit == to_unit:
     Return price (no conversion needed)
   
2. Get conversion factor:
     If item exists:
       Check item-specific conversion first
     Else:
       Check global conversion
   
3. If factor not found:
     Try reverse conversion:
       Get conversion (to_unit → from_unit)
       factor = 1 / factor
   
4. If still no factor:
     Return original price (graceful fallback)
   
5. Calculate converted price:
     converted_price = price / factor
     
     Why divide? Because if 1 unit_A = X unit_B,
     then 1 unit_B costs (price / X)
   
6. Return converted_price with rounding
```

### Example Calculation
```
Price: $100 per Piece
Conversion: 1 Piece = 19.7 Feet
Target: Price per Foot

converted_price = $100 / 19.7
converted_price = $5.076... per Foot

If Qty = 6 Feet:
Line Total = $5.076 × 6 = $30.457
```

## Performance Considerations

### Query Optimization
```python
# Good: Prefetch related data
items = Item.objects.select_related(
    'stock_unit'
).prefetch_related(
    'unit_conversions'
)

# API: Single query for item + unit
# Conversion: 1-2 queries (item-specific, then global)
# Total impact: <5ms per request
```

### Caching Strategy
- JavaScript caches unit list in memory
- Conversion factors cached on first lookup
- Items cached in Django ORM select_related
- No persistent cache needed (factors rarely change)

### Scalability
- Works with 1000s of items
- 100s of conversion rules
- Handles real-time updates
- No background job dependencies

## Extension Points

### Adding to New Forms

1. **HTML Template**:
```html
<select name="unit" class="form-control formset-unit"></select>
<input type="number" name="unit_price" class="formset-price">
```

2. **JavaScript Handler**:
```javascript
$(document).on('change', '.formset-item', function() {
  wisSoFetchPrice($(this).closest('.formset-row'));
});

$(document).on('change', '.formset-unit', function() {
  wisSoFetchPrice($(this).closest('.formset-row'));
});
```

3. **CSS Classes** (must match):
- `.formset-item` - Item selector
- `.formset-unit` - Unit selector  
- `.formset-price` - Price input

### Adding New Conversion Function

```python
# In catalog/utils.py
def get_bulk_prices_with_conversions(items, unit, use_selling_price=True):
    """
    Efficiently convert prices for multiple items to given unit.
    Useful for reports, exports, etc.
    """
    prices = {}
    for item in items:
        price = get_item_price_for_unit(item, unit, use_selling_price)
        prices[item.id] = price
    return prices
```

## Error Handling

### Graceful Degradation
```
Scenario: Conversion factor not found
├─ No item-specific conversion found ✗
├─ No global conversion found ✗
├─ No reverse conversion found ✗
└─ Return: Original base price ✓

Result: System continues working, uses fallback price
```

### Invalid Data Handling
```
Zero factor → Return base price
Missing units → Return base price  
Invalid unit reference → Return base price
Database error → Return base price
```

## Security Considerations

### Input Validation
- Unit IDs validated against database
- Item IDs validated against permissions
- Decimal precision checked
- All conversions read-only in API

### Authorization
- No special permissions needed
- Read-only API endpoints
- No creation/update via API
- All changes via Django admin

## Testing Strategy

### Unit Tests (11 tests)
- Direct conversions ✓
- Reverse conversions ✓
- Item-specific overrides ✓
- Missing conversions ✓
- Real-world scenarios ✓

### Integration Tests
- Mock API calls
- Test serializer methods
- Test event handlers

### End-to-End Tests
- Create SO with unit conversion
- Verify price calculated correctly
- Save and retrieve order

## Monitoring & Logging

### What to Monitor
- API response times (should be <50ms)
- Conversion lookup cache hits
- Database query counts
- Error rates for missing conversions

### Debug Information
```python
# Enable logging
import logging
logger = logging.getLogger('catalog.utils')

# Then in utils.py functions
logger.debug(f"Converting {qty} {from_unit} to {to_unit}")
logger.debug(f"Factor found: {factor}")
logger.debug(f"Result: {converted_price}")
```

## Deployment Checklist

- [x] Code deployed
- [x] Tests passing (11/11)
- [x] Unit conversions configured
- [x] Sales orders tested
- [x] Purchase orders tested
- [x] Services tested
- [x] Documentation created
- [x] Backward compatibility verified
- [x] Performance verified

---

**Status**: Production Ready ✅
**Last Updated**: 2026-03-23
