# Service Form Payment Field Fix - Summary

## Overview
Fixed the service form to properly handle customer payments by removing the deprecated `amount` field and ensuring `partial_payment_amount` is always visible and properly positioned.

## Changes Made

### 1. **Removed Deprecated `amount` Field** (`services/forms.py`)

#### Before:
```python
fields = [
    'service_number', 'service_name', 'customer_name',
    'service_date', 'address', 'payment_status', 'partial_payment_amount',
    'amount', 'quotation', 'discount_type', 'discount_value',  # ← amount was here
    'warehouse', 'notes',
]
```

#### After:
```python
fields = [
    'service_number', 'service_name', 'customer_name',
    'service_date', 'address', 'payment_status', 'partial_payment_amount',
    'quotation', 'discount_type', 'discount_value',  # ← amount removed
    'warehouse', 'notes',
]
```

**Reason**: The `amount` field was deprecated and no longer needed. The `partial_payment_amount` field handles all payment tracking.

### 2. **Updated Help Text** (`services/forms.py`)

Changed the help text for `partial_payment_amount` to be more accurate:

#### Before:
```python
'partial_payment_amount': 'Required when payment status is Partially Paid.'
```

#### After:
```python
'partial_payment_amount': 'Amount paid by customer (for partial or full payment).'
```

**Reason**: The field is used for tracking payments regardless of payment status (UNPAID, PARTIAL, or PAID).

### 3. **Repositioned Payment Field** (`templates/services/service_form.html`)

Moved `partial_payment_amount` from the Service Details section to the **Pricing Summary** section where it logically belongs.

#### New Location:
- **Section**: Pricing Summary
- **Position**: Between "Quotation" and "Discount"
- **Label**: "Payment Amount" (clearer than "Partial Payment Amount")
- **Icon**: Money bill icon (green)
- **Always Visible**: No longer hidden/shown based on payment status

### 4. **Removed Toggle JavaScript** (`templates/services/service_form.html`)

#### Before:
```javascript
function svcTogglePartialPayment() {
  var status = $('#id_payment_status').val();
  var show = status === 'PARTIAL';
  $('#svc-partial-payment-group').toggle(show);
  if (!show) {
    $('#id_partial_payment_amount').val('');
  }
}
```

#### After:
```javascript
// Removed - field is now always visible
```

**Reason**: The payment amount field should always be visible so users can enter payments regardless of the payment status.

## How It Works Now

### Payment Status Logic

The form now properly handles all three payment statuses:

#### 1. **UNPAID** (No payment received)
- User can leave `partial_payment_amount` as 0 or blank
- Form validation: No special requirements
- Result: Service is marked as UNPAID

#### 2. **PARTIAL** (Some payment received)
- User enters the amount paid in `partial_payment_amount`
- Form validation:
  - Must be greater than 0
  - Cannot exceed quotation amount
- Result: Service is marked as PARTIAL with the payment amount recorded

#### 3. **PAID** (Fully paid)
- User can enter the full amount in `partial_payment_amount`
- Form automatically sets `partial_payment_amount = quotation` on save
- Result: Service is marked as PAID

### Form Validation

The `clean()` method in `CustomerServiceForm` handles the logic:

```python
def clean(self):
    cleaned_data = super().clean()
    payment_status = cleaned_data.get('payment_status')
    partial_payment_amount = cleaned_data.get('partial_payment_amount')
    quotation = cleaned_data.get('quotation') or 0

    if payment_status == ServicePaymentStatus.PARTIAL:
        # Validate partial payment
        if partial_payment_amount in (None, ''):
            self.add_error('partial_payment_amount', 'Enter the partial payment amount.')
        elif partial_payment_amount <= 0:
            self.add_error('partial_payment_amount', 'Partial payment amount must be greater than 0.')
        elif quotation and partial_payment_amount > quotation:
            self.add_error('partial_payment_amount', 'Partial payment amount cannot exceed the quotation amount.')
    
    elif payment_status == ServicePaymentStatus.PAID:
        # Auto-set to full quotation amount
        cleaned_data['partial_payment_amount'] = quotation
    
    else:  # UNPAID
        # Set to 0
        cleaned_data['partial_payment_amount'] = 0

    return cleaned_data
```

## UI Layout

### Pricing Summary Section

The Pricing Summary section now has a clean 3-column layout:

```
┌─────────────────────────────────────────────────────────────┐
│                    PRICING SUMMARY                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │  Quotation   │  │Payment Amount│  │   Discount   │     │
│  │  ₱ [____]    │  │  ₱ [____]    │  │  [Type][Val] │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              Live Totals                            │   │
│  │  Quotation:              ₱ 0.00                     │   │
│  │  — Product Lines:        ₱ 0.00                     │   │
│  │  — Other Materials:      ₱ 0.00                     │   │
│  │  — Bundles:              ₱ 0.00                     │   │
│  │  Net (before discount):  ₱ 0.00                     │   │
│  │  — Discount:             ₱ 0.00                     │   │
│  │  Grand Total:            ₱ 0.00                     │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## Benefits

### 1. **Clearer User Experience**
- Payment field is always visible (no hidden fields)
- Logical grouping with other pricing fields
- Clear label: "Payment Amount" instead of "Partial Payment Amount"

### 2. **Simplified Code**
- Removed deprecated `amount` field
- Removed unnecessary JavaScript toggle logic
- Single field for all payment tracking

### 3. **Better Data Integrity**
- Form validation ensures payment amounts are valid
- Auto-calculation for PAID status
- Clear relationship between payment_status and partial_payment_amount

### 4. **Consistent Behavior**
- Same field used for partial and full payments
- No confusion about which field to use
- Validation rules are clear and enforced

## Migration Notes

### Existing Data
- Services with `amount` field set will retain that data in the database
- The field is not removed from the model (only from the form)
- This ensures backward compatibility with existing data

### Future Cleanup
If you want to completely remove the `amount` field from the database:

1. Create a data migration to copy any `amount` values to `partial_payment_amount` if needed
2. Create a schema migration to drop the `amount` column
3. Remove the field from the `CustomerService` model

## Testing Checklist

- [ ] Create a new service with UNPAID status (leave payment amount as 0)
- [ ] Create a new service with PARTIAL status (enter partial payment)
- [ ] Create a new service with PAID status (verify auto-calculation)
- [ ] Edit an existing service and change payment status
- [ ] Verify validation errors for invalid payment amounts
- [ ] Check that payment amount appears in Pricing Summary section
- [ ] Confirm no JavaScript errors in browser console
- [ ] Test form submission with various payment scenarios

## Summary

The service form now properly handles customer payments using a single, always-visible `partial_payment_amount` field in the Pricing Summary section. The deprecated `amount` field has been removed from the form, simplifying the user experience and code maintenance.

**Key Takeaway**: Use `partial_payment_amount` for all payment tracking, regardless of whether it's a partial or full payment. The `payment_status` field indicates the payment state, while `partial_payment_amount` records the actual amount paid.
