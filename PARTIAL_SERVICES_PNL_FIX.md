# Partial Services in PNL Breakdown - Fix Summary

## Problem

Partial payments for services were not showing in the PNL Breakdown modal's "Partial Payments - Services" tab.

### Root Cause

The original code only looked for **invoiced** services with partial payments:

```python
# Only checked invoices with partial payments
partial_invoice_qs = Invoice.objects.filter(
    is_paid=False,
    payments__isnull=False,
    ...
)
```

**Issue**: Services can have `partial_payment_amount` set **before** they're invoiced. The system was missing these non-invoiced services with partial payments.

## Solution

Added a separate query to capture **non-invoiced services** with partial payments.

### New Logic Flow

1. **Query 1**: Invoiced services with partial payments (existing logic)
   - Services that have been invoiced
   - Invoice has payments but not fully paid
   
2. **Query 2**: Non-invoiced services with partial payments (NEW)
   - Services with `invoice__isnull=True`
   - Services with `partial_payment_amount > 0`
   - Services with `payment_status = PARTIAL`
   - Excludes cancelled services

### Code Changes

#### Added Non-Invoiced Services Query

```python
# ── Non-Invoiced Services with Partial Payments ────────────────────
non_invoiced_services_qs = CustomerService.objects.filter(
    invoice__isnull=True,  # Not yet invoiced
    partial_payment_amount__gt=0,  # Has received payment
    payment_status=ServicePaymentStatus.PARTIAL,  # Status is PARTIAL
).exclude(
    status=ServiceStatus.CANCELLED  # Exclude cancelled services
)

# Date filter: use service_date
if date_from:
    non_invoiced_services_qs = non_invoiced_services_qs.filter(service_date__gte=date_from)
if date_to:
    non_invoiced_services_qs = non_invoiced_services_qs.filter(service_date__lte=date_to)
```

#### Calculate COGS for Non-Invoiced Services

```python
for svc in non_invoiced_services_qs:
    # Calculate payment percentage
    payment_amount = svc.partial_payment_amount or Decimal('0')
    payment_percentage = (payment_amount / svc.grand_total) if svc.grand_total > 0 else Decimal('0')
    
    # Calculate COGS components
    lines_cogs = sum(...)  # Product lines
    other_mat_cogs = sum(...)  # Other materials
    bundle_cogs = ...  # Bundles
    
    full_cogs = lines_cogs + other_mat_cogs + bundle_cogs
    proportional_cogs = (full_cogs * payment_percentage).quantize(Decimal('0.01'))
    
    # Add to breakdown
    partial_services_revenue += payment_amount
    partial_services_cogs += proportional_cogs
```

#### Created Pseudo-Invoice for Template Compatibility

Since the template expects an `invoice` object, we create a pseudo-invoice for non-invoiced services:

```python
class PseudoInvoice:
    def __init__(self, svc):
        self.invoice_number = f"(Not Invoiced)"
        self.customer_name = svc.customer_name
        self.date = svc.service_date
        self.grand_total = svc.grand_total
        self.balance_due = svc.grand_total - (svc.partial_payment_amount or Decimal('0'))
```

## How It Works Now

### Scenario 1: Service with Partial Payment (Not Invoiced)

**Example**:
- Service created: SVC-001
- Grand Total: ₱10,000
- Customer pays: ₱4,000 (40%)
- Payment Status: PARTIAL
- Invoice: None (not yet invoiced)

**Result**:
- ✅ **Now appears** in "Partial Payments - Services" tab
- Revenue recognized: ₱4,000
- COGS recognized: 40% of full COGS
- Invoice #: "(Not Invoiced)"

### Scenario 2: Service with Partial Payment (Invoiced)

**Example**:
- Service created: SVC-002
- Invoice created: INV-001
- Grand Total: ₱15,000
- Customer pays: ₱9,000 (60%)
- Payment Status: PARTIAL
- Invoice: INV-001 (has invoice)

**Result**:
- ✅ **Appears** in "Partial Payments - Services" tab
- Revenue recognized: ₱9,000
- COGS recognized: 60% of full COGS
- Invoice #: INV-001

### Scenario 3: Service Fully Paid

**Example**:
- Service created: SVC-003
- Invoice created: INV-002
- Grand Total: ₱8,000
- Customer pays: ₱8,000 (100%)
- Payment Status: PAID
- Invoice: INV-002 (fully paid)

**Result**:
- ✅ **Appears** in "Invoices" tab (not partial payments tab)
- Full revenue and COGS recognized

## COGS Calculation Details

### For Non-Invoiced Services

COGS is calculated from the service's components:

1. **Product Lines COGS**:
   ```python
   lines_cogs = sum(
       line.qty * line.item.cost_price
       for line in svc.lines.all()
       if not line.is_scrap  # Exclude scrap items
   )
   ```

2. **Other Materials COGS**:
   ```python
   other_mat_cogs = sum(
       mat.line_cost  # Uses unit_cost or falls back to unit_price
       for mat in svc.other_materials.all()
   )
   ```

3. **Bundle COGS**:
   ```python
   bundle_cogs = sum(
       pli.item.cost_price * pli.qty * bundle.qty
       for bundle in svc.bundles.all()
       for pli in bundle.price_list.items.all()
   )
   ```

4. **Proportional COGS**:
   ```python
   full_cogs = lines_cogs + other_mat_cogs + bundle_cogs
   proportional_cogs = full_cogs * payment_percentage
   ```

### For Invoiced Services

COGS is calculated using the existing `compute_invoice_cogs()` function, which handles all invoice types (POS, Sales Orders, Services).

## Date Filtering

### Non-Invoiced Services
- Filtered by `service_date` (when the service was scheduled/performed)
- **Limitation**: Not filtered by payment date since there's no payment record yet
- **Recommendation**: Consider adding a `payment_date` field to CustomerService for more accurate reporting

### Invoiced Services
- Filtered by `payments__date` (when payments were received)
- More accurate for period-based reporting

## Template Display

The breakdown modal shows both types of services in the same tab:

```
┌─────────────────────────────────────────────────────────────┐
│ Partial Payments - Services Tab                            │
├─────────────────────────────────────────────────────────────┤
│ Invoice #         │ Service #  │ Customer  │ Amount Paid   │
├─────────────────────────────────────────────────────────────┤
│ INV-001          │ SVC-002    │ John Doe  │ ₱9,000 (60%)  │
│ (Not Invoiced)   │ SVC-001    │ Jane Smith│ ₱4,000 (40%)  │
└─────────────────────────────────────────────────────────────┘
```

## Debug Information

Updated debug variables to help troubleshoot:

- `debug_total_partial_invoices`: Total invoices with partial payments
- `debug_services_with_partial`: Total services with partial payments (invoiced + non-invoiced)
- `debug_services_not_invoiced`: Count of non-invoiced services with partial payments
- `debug_so_with_partial`: Sales orders/POS with partial payments

## Benefits

### 1. **Complete Revenue Recognition**
- Captures ALL partial payments, not just invoiced ones
- More accurate P&L reporting

### 2. **Better Cash Flow Visibility**
- See payments received even before invoicing
- Track partial payments from service creation

### 3. **Accurate COGS Matching**
- COGS is calculated proportionally for all partial payments
- Maintains matching principle (revenue matched with costs)

### 4. **Flexible Workflow Support**
- Supports businesses that collect payments before invoicing
- Supports businesses that invoice immediately
- Works with both workflows seamlessly

## Testing Checklist

- [ ] Create a service with partial payment (don't invoice it)
- [ ] Verify it appears in "Partial Payments - Services" tab
- [ ] Check that revenue and COGS are proportional
- [ ] Verify invoice # shows "(Not Invoiced)"
- [ ] Create an invoice for the service
- [ ] Verify it still appears in partial payments tab
- [ ] Make final payment to complete the invoice
- [ ] Verify it moves to "Invoices" tab
- [ ] Check that totals in P&L include both invoiced and non-invoiced partial payments
- [ ] Test date filtering with various date ranges

## Future Improvements

### 1. Add Payment Date Field
Consider adding a `payment_date` field to CustomerService:

```python
payment_date = models.DateField(
    null=True, blank=True,
    help_text='Date when partial payment was received'
)
```

**Benefits**:
- More accurate date filtering
- Better period-based reporting
- Clearer audit trail

### 2. Multiple Partial Payments
Currently, `partial_payment_amount` is a single field. Consider:
- Creating a ServicePayment model (similar to InvoicePayment)
- Track multiple partial payments with dates
- Better payment history

### 3. Payment Method Tracking
Add payment method to services:
- Track how customers paid (cash, card, etc.)
- Include in payment method breakdown
- Better reconciliation

## Summary

The fix ensures that **all services with partial payments** appear in the PNL breakdown, whether they've been invoiced or not. This provides:

✅ Complete revenue recognition  
✅ Accurate COGS matching  
✅ Better cash flow visibility  
✅ Support for flexible workflows  

**Key Takeaway**: Services with `partial_payment_amount > 0` and `payment_status = PARTIAL` now appear in the PNL breakdown, even if they haven't been invoiced yet.
