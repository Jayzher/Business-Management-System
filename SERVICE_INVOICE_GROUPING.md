# Service Invoice Grouping - Multiple Services, One Invoice

## Overview
The system now automatically groups multiple services for the same customer into a single invoice when completed on the same day. This reduces invoice clutter and provides a consolidated bill for customers.

## How It Works

### Scenario 1: Single Service
```
Customer: John Doe
Date: 2026-05-31

Service SVC-001: AC Repair (₱2,000)
↓ Complete
Invoice INV-000123 created
- Line: AC Repair [SVC-001] - ₱2,000
- Total: ₱2,000
```

### Scenario 2: Multiple Services, Same Customer, Same Day
```
Customer: John Doe
Date: 2026-05-31

Service SVC-001: AC Repair (₱2,000)
↓ Complete
Invoice INV-000123 created
- Line: AC Repair [SVC-001] - ₱2,000
- Total: ₱2,000

Service SVC-002: Refrigerator Repair (₱1,500)
↓ Complete
Invoice INV-000123 UPDATED (not new invoice)
- Line: AC Repair [SVC-001] - ₱2,000
- Line: Refrigerator Repair [SVC-002] - ₱1,500
- Total: ₱3,500
```

### Scenario 3: Different Customer
```
Customer: Jane Smith
Date: 2026-05-31

Service SVC-003: Washing Machine Repair (₱1,000)
↓ Complete
Invoice INV-000124 created (NEW invoice, different customer)
- Line: Washing Machine Repair [SVC-003] - ₱1,000
- Total: ₱1,000
```

### Scenario 4: Same Customer, Different Day
```
Customer: John Doe
Date: 2026-06-01 (next day)

Service SVC-004: TV Repair (₱800)
↓ Complete
Invoice INV-000125 created (NEW invoice, different day)
- Line: TV Repair [SVC-004] - ₱800
- Total: ₱800
```

### Scenario 5: Invoice Already Paid
```
Customer: John Doe
Date: 2026-05-31

Service SVC-001: AC Repair (₱2,000)
↓ Complete
Invoice INV-000123 created and PAID
- Line: AC Repair [SVC-001] - ₱2,000
- Total: ₱2,000
- Status: PAID

Service SVC-002: Refrigerator Repair (₱1,500)
↓ Complete
Invoice INV-000126 created (NEW invoice, previous one is paid)
- Line: Refrigerator Repair [SVC-002] - ₱1,500
- Total: ₱1,500
- Status: UNPAID
```

## Grouping Criteria

An existing invoice is reused if ALL of the following conditions are met:

1. ✅ **Same customer name** (case-insensitive match)
2. ✅ **Same date** (completed on the same day)
3. ✅ **Not void** (invoice is still valid)
4. ✅ **Not fully paid** (invoice is unpaid or partially paid)
5. ✅ **Service invoice only** (not linked to Sales Order or POS Sale)

If ANY condition fails, a NEW invoice is created.

## Invoice Line Identification

To prevent duplicate lines when grouping services, each line is prefixed with the service number:

### Quotation-Based Services
```
Item Code: SVC-QUOT-SVC-001
Item Name: AC Repair (Balance after ₱500 partial payment) [SVC-001]
```

### Item-Based Services
```
Item Code: SVC-001-PART-123
Item Name: Compressor [SVC-001]

Item Code: SVC-002-PART-456
Item Name: Thermostat [SVC-002]
```

### Other Materials
```
Item Code: SVC-001-MAT-Freon
Item Name: Freon [SVC-001]
```

### Generic Service Lines
```
Item Code: SVC-SVC-001
Item Name: AC Repair [SVC-001]
```

## Invoice Notes

When services are grouped, the invoice notes show all included services:

```
Service: AC Repair (SVC-001)
+ Service: Refrigerator Repair (SVC-002)
+ Service: TV Repair (SVC-003)
```

## Benefits

### For Customers
- ✅ Single invoice for multiple services on the same day
- ✅ Easier to track and pay
- ✅ Cleaner records

### For Business
- ✅ Reduced invoice count
- ✅ Easier reconciliation
- ✅ Better cash flow (one payment for multiple services)
- ✅ Professional appearance

### For Accounting
- ✅ Accurate revenue tracking
- ✅ No duplicate invoices
- ✅ Clear service breakdown
- ✅ Proper COGS calculation

## User Messages

### First Service Completed
```
✓ Service SVC-001 completed. Invoice INV-000123 generated.
```

### Additional Service Completed (Grouped)
```
✓ Service SVC-002 completed. Invoice INV-000123 updated with 3 new item(s).
```

### Service Completed (New Invoice - Different Day)
```
✓ Service SVC-003 completed. Invoice INV-000124 generated.
```

### Service Completed (New Invoice - Already Paid)
```
✓ Service SVC-004 completed. Invoice INV-000125 generated.
(Previous invoice INV-000123 was already paid)
```

## Edge Cases

### Case 1: Customer Name Mismatch
```
Service 1: Customer = "John Doe"
Service 2: Customer = "john doe" (lowercase)
Result: GROUPED (case-insensitive match)

Service 3: Customer = "John  Doe" (extra space)
Result: GROUPED (whitespace trimmed)

Service 4: Customer = "John D."
Result: NEW INVOICE (different name)
```

### Case 2: Partial Payment
```
Service 1: Quotation ₱5,000, Partial Payment ₱2,000
→ Invoice shows ₱3,000 remaining

Service 2: Quotation ₱3,000, No Partial Payment
→ Invoice updated to ₱6,000 total (₱3,000 + ₱3,000)
```

### Case 3: Mixed Service Types
```
Service 1: Quotation-based (₱5,000)
→ Invoice Line: Service quotation [SVC-001] - ₱5,000

Service 2: Item-based (Part A: ₱1,000, Part B: ₱500)
→ Invoice Lines:
  - Part A [SVC-002] - ₱1,000
  - Part B [SVC-002] - ₱500

Total: ₱6,500
```

### Case 4: Service Already Linked to Invoice
```
Service 1: Completed → Invoice INV-000123
Service 1: Manually changed to IN_PROGRESS (via admin)
Service 1: Completed again → Invoice INV-000123 UPDATED (same invoice)
```

## Database Schema

### CustomerService Model
```python
class CustomerService(models.Model):
    service_number = CharField(unique=True)
    customer_name = CharField()
    invoice = ForeignKey('Invoice', null=True)  # Links to invoice
    # ... other fields
```

### Invoice Model
```python
class Invoice(models.Model):
    invoice_number = CharField(unique=True)
    customer_name = CharField()
    date = DateField()
    is_paid = BooleanField()
    is_void = BooleanField()
    # ... other fields
    
    # Reverse relation from CustomerService
    customer_services = RelatedManager()  # Multiple services can link to one invoice
```

## SQL Queries

### Find All Services for an Invoice
```sql
SELECT cs.service_number, cs.service_name, cs.quotation
FROM services_customerservice cs
WHERE cs.invoice_id = 123;
```

### Find Invoice for a Customer on a Specific Date
```sql
SELECT i.id, i.invoice_number, i.grand_total, i.is_paid
FROM core_invoice i
WHERE LOWER(i.customer_name) = LOWER('John Doe')
  AND i.date = '2026-05-31'
  AND i.is_void = FALSE
  AND i.is_paid = FALSE
  AND i.sales_order_id IS NULL
  AND i.pos_sale_id IS NULL
ORDER BY i.created_at DESC
LIMIT 1;
```

### Count Services per Invoice
```sql
SELECT i.invoice_number, COUNT(cs.id) as service_count
FROM core_invoice i
LEFT JOIN services_customerservice cs ON cs.invoice_id = i.id
GROUP BY i.invoice_number
HAVING COUNT(cs.id) > 1
ORDER BY service_count DESC;
```

## Configuration

Currently, the grouping behavior is automatic and cannot be disabled. Future enhancements may include:

- [ ] Setting to disable grouping (always create new invoice)
- [ ] Setting to group by week instead of day
- [ ] Setting to group even if partially paid
- [ ] Manual invoice selection when completing service

## Testing

### Test Case 1: Basic Grouping
```python
def test_service_invoice_grouping():
    # Create two services for same customer
    svc1 = create_service(customer='John Doe', date='2026-05-31')
    svc2 = create_service(customer='John Doe', date='2026-05-31')
    
    # Complete first service
    complete_service(svc1)
    invoice1 = svc1.invoice
    assert invoice1 is not None
    
    # Complete second service
    complete_service(svc2)
    invoice2 = svc2.invoice
    
    # Should be same invoice
    assert invoice1.id == invoice2.id
    assert invoice1.customer_services.count() == 2
```

### Test Case 2: Different Day
```python
def test_service_invoice_different_day():
    svc1 = create_service(customer='John Doe', date='2026-05-31')
    svc2 = create_service(customer='John Doe', date='2026-06-01')
    
    complete_service(svc1)
    complete_service(svc2)
    
    # Should be different invoices
    assert svc1.invoice.id != svc2.invoice.id
```

### Test Case 3: Already Paid
```python
def test_service_invoice_already_paid():
    svc1 = create_service(customer='John Doe', date='2026-05-31')
    svc2 = create_service(customer='John Doe', date='2026-05-31')
    
    complete_service(svc1)
    invoice1 = svc1.invoice
    
    # Mark invoice as paid
    invoice1.is_paid = True
    invoice1.save()
    
    complete_service(svc2)
    
    # Should be different invoice (first one is paid)
    assert svc2.invoice.id != invoice1.id
```

## Troubleshooting

### Issue: Services Not Grouping

**Check:**
1. Customer names match exactly (case-insensitive)
2. Services completed on same date
3. Previous invoice is not paid
4. Previous invoice is not void

**Debug Query:**
```sql
-- Find potential invoice for grouping
SELECT i.*, cs.service_number
FROM core_invoice i
LEFT JOIN services_customerservice cs ON cs.invoice_id = i.id
WHERE LOWER(i.customer_name) = LOWER('John Doe')
  AND i.date = CURRENT_DATE
  AND i.is_void = FALSE
  AND i.is_paid = FALSE
  AND i.sales_order_id IS NULL
  AND i.pos_sale_id IS NULL;
```

### Issue: Duplicate Lines in Invoice

**Cause:** Service number prefix not working

**Fix:** Check that item codes include service number:
```sql
SELECT item_code, item_name, line_total
FROM core_invoiceline
WHERE invoice_id = 123;

-- Should see:
-- SVC-001-PART-123, Compressor [SVC-001], 1000.00
-- SVC-002-PART-456, Thermostat [SVC-002], 500.00
```

## Summary

The service invoice grouping feature:
- ✅ Automatically groups services for same customer on same day
- ✅ Prevents duplicate invoices
- ✅ Maintains clear service breakdown
- ✅ Respects payment status (won't add to paid invoices)
- ✅ Provides clear user feedback
- ✅ Logs all operations for debugging

This improves the user experience and ensures accurate financial records.
