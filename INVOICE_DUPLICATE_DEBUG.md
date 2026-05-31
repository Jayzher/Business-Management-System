# Invoice Duplicate Creation - Debug Analysis

## Problem
User reports that when reposting a Sales Order, duplicate invoices are being created instead of updating the existing invoice.

## Expected Workflow
1. SO created with items A, B
2. SO approved → DN1 auto-created (DRAFT)
3. DN1 posted → Invoice #1 created with items A, B
4. User updates SO to add item C
5. User updates DN1 to add item C (or creates DN2)
6. DN posted → Invoice #1 should be UPDATED to include item C
7. **ACTUAL**: Invoice #2 is created instead

## Current Implementation

### auto_create_invoice_from_delivery()
```python
if delivery.sales_order:
    # Lock SO
    SalesOrder.objects.select_for_update().filter(pk=delivery.sales_order_id).first()
    
    # Check for existing invoice
    existing = Invoice.objects.select_for_update().filter(
        sales_order=delivery.sales_order, 
        is_void=False
    ).first()
    
    if existing:
        # UPDATE logic - add new items
        return existing
    
    # CREATE new invoice
    inv = Invoice.objects.create(...)
    return inv
```

## Possible Root Causes

### 1. Multiple Delivery Notes for Same SO
- If user creates DN1, posts it (creates Invoice #1)
- Then creates DN2 for same SO, posts it
- DN2 should find Invoice #1 and update it
- **This should work** with current code

### 2. Transaction Isolation
- If the transaction hasn't committed when checking for existing invoice
- **Fixed** by adding `select_for_update()` on invoice query

### 3. Status Check Preventing Repost
- Once DN is POSTED, it cannot be posted again (status check)
- User must be creating NEW delivery notes
- **This is the likely scenario**

### 4. Invoice Query Not Finding Existing
- Query: `Invoice.objects.filter(sales_order=delivery.sales_order, is_void=False).first()`
- This should find any non-void invoice linked to the SO
- **Should work correctly**

## Testing Scenarios

### Scenario A: Single DN, Posted Once
1. Create SO with items A, B
2. Approve SO → DN1 created
3. Post DN1 → Invoice #1 created ✓
4. Update SO to add item C
5. **Cannot post DN1 again** (status = POSTED)
6. User must manually edit DN1 while DRAFT or create DN2

### Scenario B: Multiple DNs for Same SO
1. Create SO with items A, B
2. Approve SO → DN1 created
3. Post DN1 → Invoice #1 created ✓
4. Update SO to add item C
5. Manually create DN2 for same SO with item C
6. Post DN2 → Should update Invoice #1 ✓

### Scenario C: Cancelled and Recreated DN
1. Create SO with items A, B
2. Approve SO → DN1 created
3. Post DN1 → Invoice #1 created ✓
4. Cancel DN1 → Invoice #1 voided
5. Update SO to add item C
6. Approve SO again → DN2 created (DN1 is cancelled)
7. Post DN2 → Should create NEW invoice (old one is void) ✓

## Solution

The current implementation should handle all scenarios correctly. The issue might be:

1. **User workflow misunderstanding**: User might be expecting to post the same DN twice
2. **Race condition**: Multiple users posting different DNs simultaneously
3. **Bug in query**: The existing invoice is not being found

## Recommended Fix

Add logging to track what's happening:
- Log when existing invoice is found
- Log when new invoice is created
- Log the SO ID and existing invoice count

Also ensure:
- Invoice query uses `select_for_update()` ✓ (FIXED)
- Transaction wraps the entire operation ✓ (Already wrapped)
- Query checks for `is_void=False` ✓ (Already checking)
