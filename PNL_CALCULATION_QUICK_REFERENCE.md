# P&L Calculation Quick Reference

## 📊 Financial Statement Structure

```
┌─────────────────────────────────────────────────────────────┐
│                    PROFIT & LOSS STATEMENT                  │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ 📦 MATERIALS SALES (POS + Sales Orders)                     │
├─────────────────────────────────────────────────────────────┤
│ Materials Revenue (gross)                    ₱ XXX,XXX.XX   │
│ Less: Discounts                             (₱  XX,XXX.XX)  │
│ ─────────────────────────────────────────────────────────── │
│ Net Materials Revenue                        ₱ XXX,XXX.XX   │
│ Materials COGS                               ₱  XX,XXX.XX   │
│ ═════════════════════════════════════════════════════════── │
│ Materials Gross Profit                       ₱  XX,XXX.XX   │
│                                              (XX.X% margin)  │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ 🔧 SERVICES REVENUE                                         │
├─────────────────────────────────────────────────────────────┤
│ Services Revenue (gross)                     ₱ XXX,XXX.XX   │
│   ├─ From paid invoices                     ₱ XXX,XXX.XX   │
│   └─ From partial payments (not invoiced)   ₱  XX,XXX.XX   │
│ Less: Discounts                             (₱  XX,XXX.XX)  │
│ ─────────────────────────────────────────────────────────── │
│ Net Services Revenue                         ₱ XXX,XXX.XX   │
│ Services COGS (materials + labor)            ₱  XX,XXX.XX   │
│ ═════════════════════════════════════════════════════════── │
│ Services Gross Profit                        ₱  XX,XXX.XX   │
│                                              (XX.X% margin)  │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ 💰 COMBINED TOTALS                                          │
├─────────────────────────────────────────────────────────────┤
│ Total Revenue (gross)                        ₱ XXX,XXX.XX   │
│ Less: Total Discounts                       (₱  XX,XXX.XX)  │
│ ─────────────────────────────────────────────────────────── │
│ Net Revenue                                  ₱ XXX,XXX.XX   │
│ Total COGS                                   ₱  XX,XXX.XX   │
│ ═════════════════════════════════════════════════════════── │
│ TOTAL GROSS PROFIT                           ₱  XX,XXX.XX   │
│                                              (XX.X% margin)  │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ 💸 OPERATING EXPENSES                                       │
├─────────────────────────────────────────────────────────────┤
│ Salaries & Wages                             ₱  XX,XXX.XX   │
│ Rent                                         ₱  XX,XXX.XX   │
│ Utilities                                    ₱  XX,XXX.XX   │
│ Marketing                                    ₱  XX,XXX.XX   │
│ ... (other categories)                       ₱  XX,XXX.XX   │
│ ─────────────────────────────────────────────────────────── │
│ Total Operating Expenses                     ₱  XX,XXX.XX   │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ 🎯 NET PROFIT                                               │
├─────────────────────────────────────────────────────────────┤
│ NET PROFIT                                   ₱  XX,XXX.XX   │
│                                              (XX.X% margin)  │
└─────────────────────────────────────────────────────────────┘
```

---

## 🧮 Calculation Formulas

### Materials Sales
```
Materials Revenue = POS Sales + Sales Orders
Materials Net Revenue = Materials Revenue - Materials Discounts
Materials COGS = Sum of inventory costs for sold items
Materials Gross Profit = Materials Net Revenue - Materials COGS
Materials Gross Margin = (Materials Gross Profit / Materials Net Revenue) × 100
```

### Services Revenue
```
Services Revenue = Invoiced Services + Partial Payment Services
Services Net Revenue = Services Revenue - Services Discounts
Services COGS = Materials + Labor + Other Direct Costs
Services Gross Profit = Services Net Revenue - Services COGS
Services Gross Margin = (Services Gross Profit / Services Net Revenue) × 100
```

### Partial Payment Recognition
```
Payment Percentage = Partial Payment Amount / Quotation Amount
Recognized Revenue = Partial Payment Amount
Recognized COGS = Full Service COGS × Payment Percentage
Gross Profit = Recognized Revenue - Recognized COGS
```

### Combined Totals
```
Total Revenue = Materials Revenue + Services Revenue
Net Revenue = Total Revenue - Total Discounts
Total COGS = Materials COGS + Services COGS
Gross Profit = Net Revenue - Total COGS
Gross Margin = (Gross Profit / Net Revenue) × 100
```

### Net Profit
```
Net Profit = Gross Profit - Operating Expenses
Net Margin = (Net Profit / Net Revenue) × 100
```

---

## 📋 Data Sources

### Invoices (Paid)
- **Filter:** `is_paid=True`, `is_void=False`, `paid_date` within date range
- **Includes:**
  - POS Sales (materials)
  - Sales Orders (materials)
  - Service Invoices (services)

### Partial Payments
- **Filter:** `partial_payment_amount > 0`, `invoice__isnull=True`, `service_date` within date range
- **Excludes:**
  - Cancelled services
  - Services already invoiced (to prevent double-counting)

### Operating Expenses
- **Filter:** `category.is_cogs=False`, `date` within date range
- **Includes:** All non-COGS expense categories

---

## 🔍 Key Concepts

### COGS (Cost of Goods Sold)
Direct costs of producing goods or services:
- **Materials:** Inventory cost of items sold
- **Services:** Parts used + labor costs + other direct materials
- **Calculation:** Uses `calculate_line_cogs_with_conversion()` for unit conversions

### Operating Expenses (OPEX)
Indirect costs of running the business:
- Salaries & wages
- Rent & utilities
- Marketing & advertising
- Office supplies
- Insurance
- Depreciation

### Gross Profit vs Net Profit
- **Gross Profit:** Revenue - COGS (profit before operating expenses)
- **Net Profit:** Gross Profit - OPEX (final profit, "bottom line")

### Margin Calculations
- **Gross Margin:** Shows profitability of products/services
- **Net Margin:** Shows overall business profitability
- **Healthy Ranges:**
  - Gross Margin: 20%+ (good), 10-20% (acceptable), <10% (concerning)
  - Net Margin: 10%+ (good), 0-10% (acceptable), <0% (loss)

---

## 🎯 Partial Payment Logic

### Why Proportional Recognition?
Matches the **revenue recognition principle**: recognize revenue when earned, not when invoiced.

### Example Scenario
```
Service: Air Conditioning Installation
Quotation: ₱75,000
Partial Payment: ₱30,000 (40%)

Full Service COGS:
├─ Parts: ₱25,000
├─ Labor: ₱15,000
└─ Other Materials: ₱5,000
Total COGS: ₱45,000

Recognized in P&L:
├─ Revenue: ₱30,000 (40% of work paid)
├─ COGS: ₱18,000 (40% of ₱45,000)
└─ Gross Profit: ₱12,000

When Fully Invoiced:
├─ Revenue: ₱75,000 (full amount)
├─ COGS: ₱45,000 (full amount)
└─ Gross Profit: ₱30,000
```

### Double-Counting Prevention
```
Service Lifecycle:
1. Service created → Not in P&L
2. Partial payment received → In "Partial Payments" tab
3. Service completed & invoiced → Moves to "Invoices" tab
4. Invoice paid → Full revenue in "Invoices" tab only
```

**Key Rule:** A service can ONLY appear in ONE place:
- Either in "Partial Payments" (if not invoiced)
- Or in "Invoices" (if invoiced and paid)
- Never in both

---

## 📊 Report Tabs Explained

### 1. Invoices Tab
Shows all paid invoices with breakdown:
- Type (POS, SO, SVC)
- Reference number
- Invoice number
- Date
- Customer
- Payment method
- Revenue, Discount, COGS, Gross Profit

### 2. Partial Payments Tab
Shows services with partial payments not yet invoiced:
- Service number
- Status (Draft, In Progress, Completed)
- Customer
- Service date
- Quotation amount
- Partial payment amount
- Payment percentage
- Proportional COGS
- Gross profit

### 3. Payment Methods Tab
Shows payment collection summary:
- Payment method (Cash, Bank Transfer, etc.)
- Number of transactions
- Total amount collected
- Percentage of total

---

## ⚠️ Known Limitations

### 1. Date Filtering for Partial Payments
- **Current:** Filters by `service_date` (when service was scheduled)
- **Issue:** May not reflect when payment was actually received
- **Fix:** Add `partial_payment_date` field (see PARTIAL_PAYMENT_DATE_MIGRATION.md)

### 2. Multiple Partial Payments
- **Current:** Single `partial_payment_amount` field
- **Limitation:** Can't track multiple partial payments separately
- **Workaround:** Update the field with cumulative amount
- **Future:** Create `ServicePayment` model for multiple payments

### 3. Payment Method for Partial Payments
- **Current:** Not tracked
- **Impact:** Can't see payment method breakdown for partial payments
- **Fix:** Add `partial_payment_method` field

---

## 🔧 Troubleshooting

### Issue: Revenue doesn't match expectations
**Check:**
1. Date range filter (paid_date for invoices, service_date for partial payments)
2. Invoice payment status (only paid invoices are included)
3. Voided invoices (excluded from calculations)
4. Partial payments without invoices

### Issue: Service appears twice in report
**Check:**
1. Service has invoice → Should only be in "Invoices" tab
2. Service has no invoice → Should only be in "Partial Payments" tab
3. Check debug information for double-counting

### Issue: COGS seems incorrect
**Check:**
1. Item cost prices in catalog
2. Unit conversions (selling unit vs base unit)
3. Service other materials (cost vs selling price)
4. Scrap items (excluded from COGS)

### Issue: Gross margin is negative
**Possible causes:**
1. Cost price > selling price (check pricing)
2. Excessive discounts
3. Incorrect COGS calculation
4. Missing cost prices in catalog

---

## 📈 Best Practices

### 1. Regular Reconciliation
- Compare P&L with bank statements
- Verify payment method totals
- Check for missing invoices

### 2. Accurate Cost Tracking
- Keep item cost prices updated
- Track labor costs for services
- Record other material costs accurately

### 3. Proper Categorization
- Mark COGS expenses correctly
- Separate operating expenses
- Use consistent categories

### 4. Timely Recording
- Record partial payments when received
- Mark invoices as paid promptly
- Update service statuses regularly

### 5. Period Consistency
- Use consistent date ranges
- Compare same periods (month-to-month, year-to-year)
- Account for seasonality

---

## 🎓 Understanding Margins

### Gross Margin Interpretation
| Margin | Meaning | Action |
|--------|---------|--------|
| 30%+ | Excellent | Maintain pricing strategy |
| 20-30% | Good | Monitor costs |
| 10-20% | Acceptable | Review pricing or reduce costs |
| 0-10% | Concerning | Urgent review needed |
| Negative | Loss | Immediate action required |

### Net Margin Interpretation
| Margin | Meaning | Action |
|--------|---------|--------|
| 15%+ | Excellent | Sustainable growth |
| 10-15% | Good | Healthy business |
| 5-10% | Acceptable | Watch expenses |
| 0-5% | Concerning | Reduce operating costs |
| Negative | Loss | Business model review |

---

## 📚 Related Documentation

- **PARTIAL_PAYMENT_PNL_FIX.md** - Detailed explanation of partial payment fixes
- **PARTIAL_PAYMENT_DATE_MIGRATION.md** - Guide for adding payment date tracking
- **CASHFLOW_IMPLEMENTATION_COMPLETE.md** - Cash flow vs P&L differences
- **AUTOMATED_CASHFLOW_SUMMARY.md** - Cash flow reporting

---

## 🆘 Quick Help

**Q: What's the difference between Gross Profit and Net Profit?**
A: Gross Profit = Revenue - COGS (before operating expenses)
   Net Profit = Gross Profit - Operating Expenses (final profit)

**Q: Why are partial payments included?**
A: To recognize revenue earned before invoicing (accrual accounting principle)

**Q: Can I exclude partial payments?**
A: Yes, just look at the "Invoices" tab only for cash-basis reporting

**Q: How do I improve my margins?**
A: 
1. Increase prices (if market allows)
2. Reduce COGS (negotiate with suppliers, reduce waste)
3. Reduce operating expenses (optimize operations)
4. Increase sales volume (economies of scale)

**Q: What if my net profit is negative?**
A:
1. Review pricing strategy
2. Analyze cost structure
3. Reduce operating expenses
4. Focus on high-margin products/services
5. Consider business model changes

---

**Last Updated:** 2026-04-22
**Version:** 2.0
**Status:** ✅ Current
