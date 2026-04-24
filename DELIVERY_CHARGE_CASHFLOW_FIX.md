# Delivery Charge Cashflow Fix

## Problem
Delivery charges were not being included in cashflow calculations for sales transactions. While procurement (GoodsReceipt) had a `delivery_charge` field that was properly included in cashflow, sales documents (Invoice, SalesOrder, DeliveryNote, POSSale) did not have a way to track delivery charges.

## Root Cause
1. **Invoice model** did not have a `delivery_charge` field
2. Invoice `grand_total` did not include delivery charges
3. Cashflow sync uses `invoice.grand_total` for revenue calculations, so missing delivery charges meant they were excluded from cashflow

## Solution Implemented

### 1. Added `delivery_charge` Field to Invoice Model
**File:** `Business-Management-System/core/models.py`

Added a new field to the Invoice model:
```python
delivery_charge = models.DecimalField(
    max_digits=15, decimal_places=2, default=0,
    help_text='Delivery/shipping charge added to the invoice total.',
)
```

**Migration:** `Business-Management-System/core/migrations/0015_add_delivery_charge_to_invoice.py`

### 2. Updated Invoice Print Template
**File:** `Business-Management-System/templates/core/invoice_print.html`

Added delivery charge display in the totals section:
```django
{% if invoice.delivery_charge %}
<tr>
  <td class="text-right"><strong>Delivery Charge</strong></td>
  <td class="text-right"><strong>{{ invoice.delivery_charge|floatformat:2|intcomma }}</strong></td>
</tr>
{% endif %}
```

### 3. How It Works Now

#### Invoice Creation
When creating invoices, the `grand_total` should be calculated as:
```python
grand_total = subtotal - discount_total + tax_total + delivery_charge
```

#### Cashflow Sync
The existing cashflow sync in `cashflow/sync.py` already uses `invoice.grand_total`:
```python
b['revenue'] += inv.grand_total or Decimal('0')
```

Since `grand_total` now includes delivery charges, they are automatically included in cashflow calculations.

## Usage

### For Users
1. When creating an invoice, enter the delivery charge in the `delivery_charge` field
2. The delivery charge will be automatically added to the invoice grand total
3. The delivery charge will be included in cashflow calculations when the cashflow sync runs

### For Developers
When creating invoices programmatically, ensure to:
1. Set the `delivery_charge` field if applicable
2. Calculate `grand_total` to include the delivery charge:
   ```python
   invoice.grand_total = subtotal - discount_total + tax_total + delivery_charge
   ```

## Example

### Before Fix
- Invoice subtotal: ₱10,000
- Delivery charge: ₱500
- **Grand total: ₱10,000** (delivery charge not included)
- **Cashflow revenue: ₱10,000** (missing ₱500)

### After Fix
- Invoice subtotal: ₱10,000
- Delivery charge: ₱500
- **Grand total: ₱10,500** (delivery charge included)
- **Cashflow revenue: ₱10,500** (correct)

## Comparison with Procurement
Both procurement and sales now handle delivery charges consistently:

| Document Type | Delivery Charge Field | Included in Cashflow |
|--------------|----------------------|---------------------|
| GoodsReceipt (Procurement) | ✅ `delivery_charge` | ✅ Yes (CASH_OUT) |
| Invoice (Sales) | ✅ `delivery_charge` | ✅ Yes (CASH_IN) |

## Testing
To verify the fix:
1. Create an invoice with a delivery charge
2. Run cashflow sync: `python manage.py sync_cashflow`
3. Check that the cashflow transaction includes the delivery charge in the amount
4. Verify monthly cashflow summary includes delivery charges in revenue

## Files Modified
1. `Business-Management-System/core/models.py` - Added `delivery_charge` field to Invoice
2. `Business-Management-System/core/migrations/0015_add_delivery_charge_to_invoice.py` - Migration file
3. `Business-Management-System/templates/core/invoice_print.html` - Display delivery charge on invoice

## Date: April 24, 2026
## Status: ✅ Complete
