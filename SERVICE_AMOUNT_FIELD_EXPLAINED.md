# Service Amount Field - Complete Guide

## Overview
The `amount` field in the CustomerService model serves as a **manual override** for the service's grand total. This allows flexibility when the calculated total doesn't match what you want to charge the customer.

## Purpose

### What It Does
- **Overrides the calculated grand total** when set
- Allows charging a different amount than what's calculated from quotation, lines, materials, bundles, and discounts
- Useful for special pricing, negotiated rates, or simplified billing

### What It Doesn't Do
- It does NOT track payments received (use `partial_payment_amount` for that)
- It does NOT affect line item calculations
- It does NOT change COGS calculations

## How It Works

### Normal Calculation (when `amount` is NOT set)
```
Grand Total = Quotation - Product Lines Cost - Other Materials Cost - Bundle Cost - Discount
```

### With Amount Override (when `amount` IS set)
```
Grand Total = amount (ignores all other calculations)
```

## Field Relationships

### Related Fields
1. **`quotation`**: The quoted price to the customer
2. **`amount`**: Manual override for the final total (optional)
3. **`partial_payment_amount`**: Amount paid when payment_status is PARTIAL
4. **`payment_status`**: UNPAID, PARTIAL, or PAID
5. **`discount_type` & `discount_value`**: Discount applied to the service

### Payment Status Logic
- **UNPAID**: No payment received yet
  - `partial_payment_amount` = 0
  - `amount` can be set to override total
  
- **PARTIAL**: Customer paid some amount
  - `partial_payment_amount` = amount paid so far
  - `amount` can be set to override total
  - Balance due = `grand_total` - `partial_payment_amount`
  
- **PAID**: Fully paid
  - `partial_payment_amount` = `grand_total` (auto-set by form)
  - `amount` can be set to override total

## Use Cases

### Use Case 1: Simplified Flat Rate
**Scenario**: You have a complex service with many parts and materials, but you want to charge a simple flat rate.

**Example**:
- Quotation: ₱10,000
- Product lines cost: ₱3,000
- Other materials: ₱1,500
- Bundles: ₱500
- Calculated subtotal: ₱5,000
- **Set amount to: ₱8,000** (your flat rate)
- **Grand total becomes: ₱8,000** (not ₱5,000)

### Use Case 2: Negotiated Discount
**Scenario**: Customer negotiates a special price that doesn't fit your normal discount structure.

**Example**:
- Normal calculated total: ₱15,000
- Customer negotiates: ₱12,000
- **Set amount to: ₱12,000**
- **Grand total becomes: ₱12,000**

### Use Case 3: Package Deal
**Scenario**: You want to charge a package price regardless of individual item costs.

**Example**:
- Multiple services bundled together
- Individual calculations would be ₱20,000
- Package deal price: ₱16,000
- **Set amount to: ₱16,000**
- **Grand total becomes: ₱16,000**

## Form Behavior

### In the Service Form
The `amount` field appears in the **Pricing Summary** section:
- **Label**: "Amount Override"
- **Icon**: Warning icon (indicates it overrides calculations)
- **Help Text**: "Manual override for total amount (optional). If set, this overrides the calculated grand total."
- **Placeholder**: "0.00 (optional override)"

### Validation
- Field is optional (can be left blank)
- Must be a positive decimal number if set
- No validation against quotation or other amounts (intentionally flexible)

## Important Notes

### COGS Calculation
⚠️ **Important**: Setting `amount` does NOT change COGS calculations!
- COGS is still calculated from actual product lines, materials, and bundles
- This means your profit margin will be affected if you set a lower amount
- Always check the gross profit after setting a manual amount

### Invoice Generation
When an invoice is created from the service:
- Invoice `grand_total` will use the service's `grand_total` (which respects the `amount` override)
- Invoice line items still reflect the actual products/materials used
- The invoice will show the overridden amount, not the calculated total

### Reporting
- Financial reports use the `grand_total` property (which respects `amount`)
- Revenue recognition uses the overridden amount
- COGS remains based on actual items used
- Gross profit = Revenue (with override) - COGS (actual)

## Best Practices

### When to Use
✅ **Good reasons to use amount override:**
- Flat rate pricing for complex services
- Negotiated special pricing
- Package deals or promotions
- Simplified billing for regular customers
- Warranty or goodwill services at reduced rates

### When NOT to Use
❌ **Don't use amount override for:**
- Regular discounts (use discount_type and discount_value instead)
- Tracking payments (use partial_payment_amount)
- Adjusting individual line items (edit the line items directly)
- Hiding costs (this affects profit margins)

### Recommendations
1. **Document the reason**: Use the `notes` field to explain why you set a manual amount
2. **Check profit margins**: Always review the gross profit after setting an override
3. **Be consistent**: If you use flat rates, consider creating price lists instead
4. **Communicate clearly**: Make sure the customer understands what they're paying for

## Code Implementation

### Model Property
```python
@property
def grand_total(self):
    """Grand total after discount. If amount is manually set, use that instead."""
    if self.amount is not None and self.amount > 0:
        return self.amount
    return self.subtotal - self.discount_amount
```

### Form Field
```python
'amount': forms.NumberInput(attrs={
    **_NUM, 
    'placeholder': '0.00 (optional override)', 
    'id': 'id_amount'
}),
```

### Help Text
```python
'amount': 'Manual override for total amount (optional). If set, this overrides the calculated grand total.',
```

## Testing

### Test Cases
The system includes tests to verify amount override behavior:

1. **test_grand_total_uses_manual_amount_when_set**
   - Sets amount to ₱750
   - Verifies grand_total returns ₱750 (not calculated value)

2. **test_line_total_still_correct_when_manual_amount_set**
   - Sets amount to ₱999
   - Verifies line_total still calculates correctly (independent of amount)

3. **test_pnl_with_manual_amount_override**
   - Sets amount to ₱500
   - Verifies P&L calculations use the overridden amount
   - Checks that gross profit is calculated correctly

## Migration Notes

### Existing Services
- Services created before this feature have `amount = None`
- They will continue to use calculated grand_total
- No data migration needed

### Backward Compatibility
- The field is nullable and optional
- Existing code that doesn't set amount will work unchanged
- Tests verify both scenarios (with and without amount)

## Summary

The `amount` field provides flexibility for special pricing scenarios while maintaining accurate COGS tracking. Use it when you need to charge a different amount than the calculated total, but always be aware of how it affects your profit margins.

**Key Takeaway**: `amount` overrides revenue (what you charge), but COGS (what it costs you) remains based on actual items used.
