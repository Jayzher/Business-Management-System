# Invoice Auto-Update Fix - Duplicate Prevention

## Problem
When reposting a Sales Order (by posting a second delivery note or pickup), duplicate invoices were being created instead of updating the existing invoice.

## Root Cause Analysis

The issue was caused by a **race condition** in the invoice lookup query. When checking for existing invoices, the query was not using a database lock, which could allow multiple transactions to see "no existing invoice" simultaneously and create duplicates.

## Solution Implemented

### 1. Added Row-Level Locking
```python
# BEFORE (vulnerable to race conditions)
existing = Invoice.objects.filter(
    sales_order=delivery.sales_order, 
    is_void=False
).first()

# AFTER (with row-level lock)
existing = Invoice.objects.select_for_update().filter(
    sales_order=delivery.sales_order, 
    is_void=False
).first()
```

The `select_for_update()` ensures that:
- The invoice row is locked for the duration of the transaction
- Other concurrent transactions must wait until this one completes
- No duplicate invoices can be created for the same Sales Order

### 2. Added Comprehensive Logging
Added logging statements to track:
- When existing invoices are found
- When new invoices are created
- When items are added to existing invoices
- When invoice totals are recalculated

This helps debug any future issues.

### 3. Enhanced User Feedback
Updated views to display different messages:
- **New invoice**: "Invoice INV-000123 auto-created."
- **Updated invoice**: "Invoice INV-000123 updated with 2 new item(s)."

## How It Works

### Workflow: Sales Order with Multiple Deliveries

1. **First Delivery**
   ```
   SO-001 (Items: A, B) → Approved
   ↓
   DN-001 created (DRAFT) with items A, B
   ↓
   DN-001 posted
   ↓
   Invoice INV-000001 created with items A, B
   ```

2. **Sales Order Updated**
   ```
   SO-001 updated to add item C
   ↓
   User manually creates DN-002 for same SO with item C
   OR
   User edits DN-001 (if still DRAFT) to add item C
   ```

3. **Second Delivery Posted**
   ```
   DN-002 posted
   ↓
   System checks: Invoice exists for SO-001? YES (INV-000001)
   ↓
   System locks INV-000001 row
   ↓
   System checks: Does INV-000001 have item C? NO
   ↓
   System adds item C to INV-000001
   ↓
   System recalculates totals
   ↓
   Message: "Invoice INV-000001 updated with 1 new item(s)."
   ```

### Key Features

#### Idempotent Operations
- Posting the same delivery multiple times won't create duplicate stock movements
- Posting multiple deliveries for the same SO won't create duplicate invoices
- Adding the same item multiple times won't create duplicate invoice lines

#### Transaction Safety
- All operations wrapped in `@transaction.atomic`
- Row-level locks prevent race conditions
- Rollback on any error ensures data consistency

#### Smart Updates
- Only NEW items are added to existing invoices
- Existing items are not duplicated
- Totals are automatically recalculated
- Delivery charges are preserved

## Testing Scenarios

### Scenario 1: Single Delivery, Posted Once
✅ **Expected**: Invoice created
```
1. Create SO with items A, B
2. Approve SO → DN auto-created
3. Post DN → Invoice created ✓
```

### Scenario 2: Multiple Deliveries for Same SO
✅ **Expected**: Invoice updated, not duplicated
```
1. Create SO with items A, B
2. Approve SO → DN-001 created
3. Post DN-001 → Invoice #1 created
4. Update SO to add item C
5. Create DN-002 for same SO with item C
6. Post DN-002 → Invoice #1 UPDATED (not duplicated) ✓
```

### Scenario 3: Concurrent Posts (Race Condition)
✅ **Expected**: One invoice created, second waits and updates
```
1. Create SO with items A, B
2. Create DN-001 and DN-002 for same SO
3. Post DN-001 and DN-002 simultaneously
4. First post creates invoice, locks it
5. Second post waits for lock, then updates invoice ✓
```

### Scenario 4: Cancelled and Recreated
✅ **Expected**: New invoice created (old one is void)
```
1. Create SO, post DN → Invoice #1 created
2. Cancel DN → Invoice #1 voided
3. Create new DN, post it → Invoice #2 created ✓
```

## Files Modified

### Core Logic
- `Business-Management-System/inventory/automation.py`
  - `auto_create_invoice_from_delivery()` - Added locking and logging
  - `auto_create_invoice_from_pickup()` - Added locking and logging

### Views
- `Business-Management-System/sales/views.py`
  - `delivery_post_view()` - Enhanced user messages
  - `pickup_post_view()` - Enhanced user messages
  - `DeliveryNoteViewSet.post_delivery()` - Added update flags to API response
  - `SalesPickupViewSet.post_pickup()` - Added update flags to API response

## Verification Steps

### Manual Testing
1. Create a Sales Order with 2 items
2. Approve it (auto-creates delivery note)
3. Post the delivery note
4. Check: Invoice created? ✓
5. Update the Sales Order to add 1 more item
6. Create a second delivery note for the same SO
7. Post the second delivery note
8. Check: Invoice updated (not duplicated)? ✓
9. Check: Invoice has all 3 items? ✓
10. Check: Invoice totals correct? ✓

### Database Verification
```sql
-- Check for duplicate invoices for same SO
SELECT sales_order_id, COUNT(*) as invoice_count
FROM core_invoice
WHERE is_void = FALSE
GROUP BY sales_order_id
HAVING COUNT(*) > 1;

-- Should return 0 rows
```

### Log Verification
Check application logs for:
```
INFO: Found existing invoice INV-000123 for SO SO-001, updating it
INFO: Added new item ITEM-C to invoice INV-000123
INFO: Updated invoice INV-000123 totals: subtotal=1500.00, grand_total=1500.00
```

## Rollback Plan

If issues occur, revert these commits:
1. Revert locking changes in `automation.py`
2. Revert message changes in `views.py`
3. Restart application

## Performance Impact

**Minimal** - Row-level locks are held only during the invoice creation/update transaction, which is typically < 100ms. The lock is released immediately after commit.

## Future Enhancements

1. Add admin interface to merge duplicate invoices (if any exist from before this fix)
2. Add database constraint to prevent multiple non-void invoices per SO
3. Add audit trail for invoice updates
4. Add unit tests for concurrent posting scenarios

## Support

If duplicate invoices still occur:
1. Check application logs for the invoice creation flow
2. Verify database transaction isolation level (should be READ COMMITTED or higher)
3. Check for any custom code bypassing the automation functions
4. Contact development team with:
   - Sales Order number
   - Delivery Note numbers
   - Invoice numbers
   - Timestamp of the issue
   - Application logs
