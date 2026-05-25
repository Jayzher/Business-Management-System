# Why ACC-E-48-HA Shows Negative Profit (-1662.54)

## Your Transaction Data
```
Item: ACC-E-48-HA (Expanded wire # 48 Analok)
Location: SHOP-001-MAIN
Quantity: 1.00m (1 meter)
Unit Price: 185.00
Line Total: 185.00
COGS: 1847.54
Profit: -1662.54 ❌ NEGATIVE!
```

## Root Cause

This negative profit occurred because **the service invoice was created BEFORE the Services COGS fix was applied**.

### Timeline of Events

1. **Before the Fix:**
   - Services incorrectly used the **selling unit** for COGS calculation
   - When you created a service with 1 meter of wire:
     - System used `line.unit` (meter) for COGS
     - But there was NO conversion from Roll to Meter at that time
     - System fell back to using raw `cost_price` = 1847.54
     - COGS = 1847.54 (treating 1 meter as 1 roll!)

2. **After the Fix (Today):**
   - Services now correctly use the **procurement unit** (Roll) for COGS
   - Unit conversion was added: 1 Roll = 18 Meters
   - New services will calculate correctly

3. **Your Invoice:**
   - Was created with the OLD buggy code
   - COGS was stored as 1847.54 in the database
   - **Existing invoices don't automatically recalculate**

## Current Correct Configuration

The item is now properly configured:

```
Item: ACC-E-48-HA
├─ Procurement Unit: Roll
├─ Selling Unit: Meter
├─ Cost Price: 1847.54 per Roll
├─ Selling Price: 185.00 per Roll
└─ Conversion: 1 Roll = 18 Meters
   └─ Conversion Price: 185.00 per Meter
```

### Correct Calculation (for NEW services)

When you sell **1 meter**:
```
Revenue: 1m × 185.00 = 185.00
COGS: 1847.54 ÷ 18 = 102.64 per meter
Profit: 185.00 - 102.64 = 82.36 ✓ POSITIVE!
```

When you sell **1 roll (18 meters)**:
```
Revenue: 18m × 185.00 = 3,330.00
COGS: 1847.54 per roll
Profit: 3,330.00 - 1,847.54 = 1,482.46 ✓ POSITIVE!
Margin: 44.5%
```

## Why Your Invoice Still Shows Negative

**Database Storage:**
When an invoice is created, the COGS is calculated and **stored** in the `grand_total_cogs` field. This value doesn't automatically update when you fix the code or add conversions.

**Your invoice has:**
```sql
invoice.grand_total = 185.00
invoice.grand_total_cogs = 1847.54  ← Stored with old buggy calculation
invoice.profit = 185.00 - 1847.54 = -1662.54
```

## Solutions

### Option 1: Recalculate Existing Invoices (Recommended)

Run the recalculation script:

```bash
cd Business-Management-System
python recalculate_service_invoice_cogs.py
```

This will:
1. Find all service invoices with negative profit
2. Recalculate COGS using the new correct formula
3. Update the `grand_total_cogs` field
4. Show before/after comparison

**After recalculation:**
```
Invoice: [Your Invoice Number]
Old COGS: 1847.54
New COGS: 102.64
Old Profit: -1662.54
New Profit: 82.36 ✓
```

### Option 2: Manual Database Update

If you know the specific invoice ID:

```python
from invoices.models import Invoice
from core.cogs import compute_invoice_cogs

inv = Invoice.objects.get(invoice_number='YOUR_INVOICE_NUMBER')
new_cogs = compute_invoice_cogs(inv)
inv.grand_total_cogs = new_cogs
inv.save(update_fields=['grand_total_cogs', 'updated_at'])
```

### Option 3: Leave Old Invoices As-Is

If the invoice is already finalized and you don't want to change historical records:
- Keep the old COGS for accounting consistency
- New invoices will calculate correctly
- Add a note explaining the discrepancy

## Verification

To verify the fix is working for NEW services:

1. Create a new service with ACC-E-48-HA
2. Add 1 meter of the item
3. Complete the service and generate invoice
4. Check the COGS:
   - Should be: **102.64** (not 1847.54)
   - Profit should be: **82.36** (not -1662.54)

## Summary

| Aspect | Old (Buggy) | New (Fixed) |
|--------|-------------|-------------|
| **COGS Calculation** | Used selling unit (meter) | Uses procurement unit (roll) |
| **Conversion Handling** | Ignored or missing | Properly applied (1 roll = 18m) |
| **COGS for 1 meter** | 1847.54 ❌ | 102.64 ✓ |
| **Profit for 1 meter** | -1662.54 ❌ | 82.36 ✓ |
| **Existing Invoices** | Need recalculation | - |
| **New Invoices** | - | Calculate correctly ✓ |

## Next Steps

1. ✓ Unit conversion is configured correctly
2. ✓ Code fix is applied
3. ⚠️ Run `recalculate_service_invoice_cogs.py` to fix existing invoices
4. ✓ Test with a new service to verify

---

**Note:** This issue affected ALL service items with different procurement and selling units. The fix ensures accurate COGS and profit calculations going forward.
