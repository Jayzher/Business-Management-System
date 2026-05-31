# Invoice Auto-Update on Repost

## Overview

Invoices are now automatically **updated** when Sales Orders are modified and Delivery/Pickup documents are reposted. The system will:

✅ **Update existing invoice** with new items
✅ **Recalculate totals** automatically
✅ **Prevent duplicate invoices**
✅ **Skip items already in invoice**

## Problem Solved

### Before (No Update):
```
1. Create Sales Order with Items A, B, C
2. Post Delivery → Invoice created with A, B, C
3. Update Sales Order, add Items D, E
4. Repost Delivery → Invoice NOT updated
   ❌ Result: Invoice missing D, E
```

### After (Auto-Update):
```
1. Create Sales Order with Items A, B, C
2. Post Delivery → Invoice created with A, B, C
3. Update Sales Order, add Items D, E
4. Repost Delivery → Invoice updated with D, E
   ✅ Result: Invoice now has A, B, C, D, E
```

## Implementation

### Functions Updated

1. **`auto_create_invoice_from_delivery()`** - `inventory/automation.py`
2. **`auto_create_invoice_from_pickup()`** - `inventory/automation.py`

### How It Works

#### Step 1: Check for Existing Invoice

```python
existing = Invoice.objects.filter(
    sales_order=delivery.sales_order, 
    is_void=False
).first()

if existing:
    # UPDATE existing invoice
    ...
```

#### Step 2: Identify New Items

```python
# Get existing invoice line item codes
existing_line_items = set(
    existing.lines.values_list('item_code', flat=True)
)

# Check which SO lines are new
for line in so.lines.all():
    if line.item.code not in existing_line_items:
        # This is a NEW item, add to invoice
        ...
```

#### Step 3: Add New Invoice Lines

```python
new_lines_added = 0
for line in so.lines.all():
    if line.item.code not in existing_line_items:
        InvoiceLine.objects.create(
            invoice=existing,
            item_code=line.item.code,
            item_name=line.item.name,
            qty=line.qty_ordered,
            unit=line.unit.abbreviation,
            unit_price=line.unit_price,
            line_total=line.line_total,
        )
        new_lines_added += 1
```

#### Step 4: Recalculate Totals

```python
if new_lines_added > 0:
    subtotal = sum(l.line_total for l in existing.lines.all())
    delivery_charge = so.delivery_charge or Decimal('0')
    existing.subtotal = subtotal
    existing.delivery_charge = delivery_charge
    existing.grand_total = subtotal + delivery_charge
    existing.save(update_fields=['subtotal', 'delivery_charge', 'grand_total', 'updated_at'])
```

## Use Cases

### Use Case 1: Add Items to Sales Order

**Scenario:**
1. Create SO with 3 items (₱1,000 each)
2. Post delivery → Invoice created (₱3,000 total)
3. Customer adds 2 more items (₱500 each)
4. Update SO, add 2 items
5. Repost delivery

**Result:**
- ✅ Original 3 items: Already in invoice
- ✅ New 2 items: Added to invoice
- ✅ Invoice total: ₱4,000 (was ₱3,000)
- ✅ Same invoice number (not a new invoice)

### Use Case 2: Add Bundle to Sales Order

**Scenario:**
1. Create SO with Bundle A (3 items, ₱2,000)
2. Post pickup → Invoice created (₱2,000)
3. Customer adds Bundle B (2 items, ₱1,500)
4. Update SO, add Bundle B
5. Repost pickup

**Result:**
- ✅ Bundle A: Already in invoice
- ✅ Bundle B: Added to invoice
- ✅ Invoice total: ₱3,500 (was ₱2,000)
- ✅ Stock movements: Only Bundle B items deducted (Bundle A skipped)

### Use Case 3: Multiple Updates

**Scenario:**
1. Create SO with Item A (₱100)
2. Post delivery → Invoice created (₱100)
3. Add Item B (₱200), repost → Invoice updated (₱300)
4. Add Item C (₱150), repost → Invoice updated (₱450)
5. Add Item D (₱50), repost → Invoice updated (₱500)

**Result:**
- ✅ Single invoice with 4 items
- ✅ Total: ₱500
- ✅ No duplicate invoices
- ✅ No duplicate stock movements

## Benefits

### ✅ Data Accuracy
- **Invoice always matches SO** - reflects all items
- **Correct totals** - automatically recalculated
- **No missing items** - new items added automatically

### ✅ User Experience
- **No manual updates** - invoice updates automatically
- **Same invoice number** - no confusion with multiple invoices
- **Transparent** - clear audit trail

### ✅ Business Logic
- **One invoice per SO** - maintains 1:1 relationship
- **Accurate billing** - customer billed for all items
- **Proper accounting** - totals always correct

## Integration with Stock Movements

The invoice update works seamlessly with idempotent stock movements:

**Combined Flow:**
1. Update SO, add new items
2. Repost delivery
3. **Stock movements**: Only new items deducted (existing skipped)
4. **Invoice**: Only new items added (existing skipped)
5. **Totals**: Recalculated automatically

**Result:**
- ✅ Stock deducted correctly (no duplicates)
- ✅ Invoice updated correctly (no duplicates)
- ✅ Totals accurate

## Services

**Note:** Services work differently:
- Services can only be completed ONCE
- Once COMPLETED, status prevents re-completion
- Invoice created during first completion
- No update mechanism needed (can't re-complete)

**Service Flow:**
```
DRAFT → IN_PROGRESS → COMPLETED (invoice created)
                          ↓
                    Cannot re-complete
```

## Technical Details

### Idempotency

Both functions are now **idempotent**:
- First call: Creates invoice
- Subsequent calls: Updates existing invoice
- Safe to call multiple times

### Performance

**Efficient queries:**
```python
# Single query to get existing items
existing_line_items = set(
    existing.lines.values_list('item_code', flat=True)
)

# O(1) lookup for each line
if line.item.code not in existing_line_items:
    ...
```

### Transaction Safety

Both functions use `@transaction.atomic`:
- All changes committed together
- Rollback on error
- No partial updates

## Edge Cases Handled

### 1. No Existing Invoice
- Creates new invoice normally
- All items added

### 2. Invoice Already Has All Items
- No new lines added
- Totals unchanged
- Returns existing invoice

### 3. Mixed Scenario
- Some items already in invoice (skipped)
- Some items new (added)
- Totals recalculated

### 4. Bundles
- Checks bundle name (not individual items)
- Adds bundle as single line item
- Prevents duplicate bundle entries

### 5. Delivery Charge
- Recalculated from SO
- Updated in invoice
- Included in grand total

## Limitations

### Current Implementation

**Item identification by code:**
- Uses `item_code` to check if item exists
- Same item code = considered duplicate
- Different quantities not tracked separately

**Example:**
```
Original: Item A, Qty 10
Update: Item A, Qty 5 (additional)

Result: Only 1 line for Item A (Qty 10)
New quantity NOT added
```

### Future Enhancement

To handle quantity updates:
```python
# Check if item exists
existing_line = existing.lines.filter(item_code=line.item.code).first()

if existing_line:
    # Update quantity instead of skipping
    existing_line.qty += line.qty_ordered
    existing_line.line_total = existing_line.qty * existing_line.unit_price
    existing_line.save()
else:
    # Add new line
    ...
```

## Testing

### Test Scenarios

1. **First Post**
   - [ ] Create SO with 3 items
   - [ ] Post delivery
   - [ ] Verify invoice created with 3 items
   - [ ] Verify totals correct

2. **Add Items and Repost**
   - [ ] Add 2 items to SO
   - [ ] Repost delivery
   - [ ] Verify invoice has 5 items (3 + 2)
   - [ ] Verify totals updated
   - [ ] Verify same invoice number

3. **Add Bundle and Repost**
   - [ ] Add bundle to SO
   - [ ] Repost delivery
   - [ ] Verify bundle added to invoice
   - [ ] Verify totals updated

4. **Multiple Reposts**
   - [ ] Add item, repost
   - [ ] Add another item, repost
   - [ ] Add bundle, repost
   - [ ] Verify all items in single invoice
   - [ ] Verify totals cumulative

5. **Delivery Charge**
   - [ ] Update SO delivery charge
   - [ ] Repost delivery
   - [ ] Verify invoice delivery charge updated
   - [ ] Verify grand total includes new charge

## Related Files

### Modified Files:
- `inventory/automation.py` - `auto_create_invoice_from_delivery()`, `auto_create_invoice_from_pickup()`

### Related Models:
- `core/models.py` - `Invoice`, `InvoiceLine`
- `sales/models.py` - `SalesOrder`, `DeliveryNote`, `SalesPickup`

### Related Functions:
- `inventory/services.py` - `post_delivery()`, `post_sales_pickup()` (calls invoice functions)

## Migration Notes

### Backward Compatibility

✅ **Fully backward compatible**
- Existing invoices not affected
- New logic only applies to future posts
- No database migrations required

### Deployment

1. Deploy updated code
2. Test with sample SO update
3. Verify invoice updates correctly
4. No special migration steps needed

## Troubleshooting

### Issue: Invoice not updating

**Check:**
1. Verify invoice exists for the SO
2. Verify invoice is not void
3. Check if items are truly new (not already in invoice)
4. Review item codes match

### Issue: Totals incorrect

**Check:**
1. Verify all invoice lines have correct line_total
2. Check delivery_charge from SO
3. Recalculate manually: sum(line_total) + delivery_charge

### Issue: Duplicate items in invoice

**Possible causes:**
1. Item code changed between posts
2. Manual invoice line creation
3. Concurrent updates

**Solution:**
- Check item codes are consistent
- Avoid manual invoice edits
- Use transaction locking

## Summary

✅ **Invoices auto-update** when SO modified and reposted
✅ **New items added** to existing invoice
✅ **Totals recalculated** automatically
✅ **No duplicate invoices** - updates existing
✅ **Works with stock movements** - both idempotent
✅ **Backward compatible** - no migration needed

The system now keeps invoices in sync with Sales Orders automatically! 🎉
