# Partial Payment P&L - Testing Checklist

## 🎯 Purpose
Comprehensive testing checklist to verify the partial payment P&L calculations are working correctly and prevent double-counting.

---

## ✅ Pre-Testing Setup

### Environment Preparation
- [ ] Backup production database before testing
- [ ] Create test environment with sample data
- [ ] Verify all migrations are applied
- [ ] Clear browser cache
- [ ] Log in with appropriate permissions

### Test Data Requirements
- [ ] At least 5 services with partial payments
- [ ] At least 3 services with full invoices
- [ ] At least 2 services in different statuses (DRAFT, IN_PROGRESS, COMPLETED)
- [ ] At least 1 cancelled service
- [ ] Services spanning multiple months

---

## 🧪 Test Scenarios

### Scenario 1: Basic Partial Payment Recognition
**Objective:** Verify partial payment appears correctly in P&L

#### Setup
```
Service: SVC-TEST-001
Quotation: ₱100,000
Partial Payment: ₱40,000
Status: IN_PROGRESS
Invoice: NULL
Service Date: Current month
```

#### Test Steps
1. [ ] Create service with above details
2. [ ] Navigate to Financial Statement report
3. [ ] Set date range to current month
4. [ ] Click "Generate" button

#### Expected Results
- [ ] Service appears in "Partial Payments" tab
- [ ] Revenue shows ₱40,000
- [ ] Payment percentage shows 40%
- [ ] COGS is proportional (40% of full COGS)
- [ ] Gross profit is calculated correctly
- [ ] Service does NOT appear in "Invoices" tab

#### Verification Queries
```sql
-- Check service state
SELECT service_number, quotation, partial_payment_amount, 
       status, payment_status, invoice_id
FROM services_customerservice
WHERE service_number = 'SVC-TEST-001';

-- Expected: partial_payment_amount = 40000, invoice_id = NULL
```

---

### Scenario 2: Partial Payment → Full Invoice (No Double-Counting)
**Objective:** Verify service moves from partial to invoice without double-counting

#### Setup
```
Service: SVC-TEST-002
Quotation: ₱75,000
Partial Payment: ₱30,000
Status: IN_PROGRESS → COMPLETED
Invoice: NULL → Created → Paid
Service Date: Current month
```

#### Test Steps - Part A: Partial Payment
1. [ ] Create service with ₱75,000 quotation
2. [ ] Set partial payment to ₱30,000
3. [ ] Run Financial Statement for current month
4. [ ] Verify service in "Partial Payments" tab
5. [ ] Note the revenue: ₱30,000

#### Test Steps - Part B: Create Invoice
6. [ ] Complete the service
7. [ ] Create invoice for ₱75,000
8. [ ] Link invoice to service
9. [ ] Run Financial Statement again
10. [ ] Verify service is REMOVED from "Partial Payments" tab
11. [ ] Verify service is NOT in "Invoices" tab (invoice not paid yet)

#### Test Steps - Part C: Pay Invoice
12. [ ] Mark invoice as paid
13. [ ] Set paid_date to current month
14. [ ] Run Financial Statement again
15. [ ] Verify service appears in "Invoices" tab
16. [ ] Verify revenue shows ₱75,000 (not ₱105,000)
17. [ ] Verify service is NOT in "Partial Payments" tab

#### Expected Results
- [ ] Service appears in only ONE tab at a time
- [ ] Total revenue = ₱75,000 (not ₱30,000 + ₱75,000)
- [ ] No double-counting detected
- [ ] COGS matches full service COGS
- [ ] Gross profit is correct

#### Verification Queries
```sql
-- Check final state
SELECT s.service_number, s.quotation, s.partial_payment_amount,
       i.invoice_number, i.grand_total, i.is_paid, i.paid_date
FROM services_customerservice s
LEFT JOIN core_invoice i ON s.invoice_id = i.id
WHERE s.service_number = 'SVC-TEST-002';

-- Expected: invoice_id NOT NULL, is_paid = TRUE
```

---

### Scenario 3: Multiple Partial Payments
**Objective:** Verify cumulative partial payments are recognized correctly

#### Setup
```
Service: SVC-TEST-003
Quotation: ₱150,000
Partial Payment 1: ₱50,000
Partial Payment 2: ₱50,000 (cumulative: ₱100,000)
Status: IN_PROGRESS
Invoice: NULL
```

#### Test Steps
1. [ ] Create service with ₱150,000 quotation
2. [ ] Set partial payment to ₱50,000
3. [ ] Run Financial Statement
4. [ ] Verify revenue: ₱50,000 (33.3%)
5. [ ] Update partial payment to ₱100,000
6. [ ] Run Financial Statement again
7. [ ] Verify revenue: ₱100,000 (66.7%)

#### Expected Results
- [ ] First run: ₱50,000 revenue, 33.3% recognition
- [ ] Second run: ₱100,000 revenue, 66.7% recognition
- [ ] COGS proportional to payment percentage
- [ ] Service remains in "Partial Payments" tab

---

### Scenario 4: Overpayment Protection
**Objective:** Verify payment percentage is capped at 100%

#### Setup
```
Service: SVC-TEST-004
Quotation: ₱50,000
Partial Payment: ₱60,000 (120% - overpayment)
Status: IN_PROGRESS
Invoice: NULL
```

#### Test Steps
1. [ ] Create service with ₱50,000 quotation
2. [ ] Set partial payment to ₱60,000
3. [ ] Run Financial Statement
4. [ ] Check payment percentage

#### Expected Results
- [ ] Revenue shows ₱60,000
- [ ] Payment percentage capped at 100%
- [ ] COGS = 100% of full COGS (not 120%)
- [ ] No over-recognition of costs

---

### Scenario 5: Cancelled Service Exclusion
**Objective:** Verify cancelled services are excluded

#### Setup
```
Service: SVC-TEST-005
Quotation: ₱80,000
Partial Payment: ₱30,000
Status: CANCELLED
Invoice: NULL
```

#### Test Steps
1. [ ] Create service with partial payment
2. [ ] Mark service as CANCELLED
3. [ ] Run Financial Statement
4. [ ] Check both "Invoices" and "Partial Payments" tabs

#### Expected Results
- [ ] Service does NOT appear in "Partial Payments" tab
- [ ] Service does NOT appear in "Invoices" tab
- [ ] Debug info shows service excluded

---

### Scenario 6: Date Range Filtering
**Objective:** Verify date filtering works correctly

#### Setup
```
Service A: service_date = January 15
Service B: service_date = February 15
Service C: service_date = March 15
All have partial payments, no invoices
```

#### Test Steps
1. [ ] Create three services in different months
2. [ ] Run Financial Statement for January only
3. [ ] Verify only Service A appears
4. [ ] Run Financial Statement for February only
5. [ ] Verify only Service B appears
6. [ ] Run Financial Statement for Q1 (Jan-Mar)
7. [ ] Verify all three services appear

#### Expected Results
- [ ] Date filtering works correctly
- [ ] Only services in date range appear
- [ ] Count matches debug information

#### Known Limitation
⚠️ **Note:** Currently filters by `service_date`, not actual payment date. This may cause inaccuracies if payment was received on a different date.

---

### Scenario 7: Service Without Invoice (Long-term Partial)
**Objective:** Verify service stays in partial payments until invoiced

#### Setup
```
Service: SVC-TEST-007
Quotation: ₱100,000
Partial Payment: ₱25,000
Status: DRAFT (for 3 months)
Invoice: NULL
```

#### Test Steps
1. [ ] Create service with partial payment
2. [ ] Run Financial Statement for Month 1
3. [ ] Verify service appears
4. [ ] Wait (or change service_date to Month 2)
5. [ ] Run Financial Statement for Month 2
6. [ ] Verify service still appears
7. [ ] Repeat for Month 3

#### Expected Results
- [ ] Service appears in all three months
- [ ] Revenue consistently ₱25,000
- [ ] COGS consistently proportional
- [ ] Service remains until invoiced

---

### Scenario 8: Mixed Revenue Sources
**Objective:** Verify correct separation of materials vs services revenue

#### Setup
```
POS Sale: ₱50,000 (materials)
Sales Order: ₱75,000 (materials)
Service Invoice: ₱100,000 (services)
Service Partial: ₱30,000 (services)
```

#### Test Steps
1. [ ] Create and pay POS sale
2. [ ] Create and pay sales order
3. [ ] Create and pay service invoice
4. [ ] Create service with partial payment
5. [ ] Run Financial Statement

#### Expected Results
- [ ] Materials Revenue = ₱125,000 (POS + SO)
- [ ] Services Revenue = ₱130,000 (Invoice + Partial)
- [ ] Total Revenue = ₱255,000
- [ ] Separate COGS for materials and services
- [ ] Separate gross profit calculations

---

## 🔍 Debug Information Verification

### Check Debug Counts
For each test run, verify debug information:

- [ ] Total non-cancelled services matches database count
- [ ] Services with partial_payment_amount > 0 is accurate
- [ ] Services not yet invoiced count is correct
- [ ] Services with payment_status=PARTIAL matches
- [ ] Services already counted in invoices is accurate
- [ ] Final query count matches displayed services

### SQL Verification Queries
```sql
-- Total non-cancelled services
SELECT COUNT(*) FROM services_customerservice
WHERE status != 'CANCELLED';

-- Services with partial payments
SELECT COUNT(*) FROM services_customerservice
WHERE partial_payment_amount > 0
  AND status != 'CANCELLED';

-- Services with partial payments NOT invoiced
SELECT COUNT(*) FROM services_customerservice
WHERE partial_payment_amount > 0
  AND invoice_id IS NULL
  AND status != 'CANCELLED';

-- Services with PARTIAL payment status
SELECT COUNT(*) FROM services_customerservice
WHERE payment_status = 'PARTIAL'
  AND status != 'CANCELLED';
```

---

## 📊 Report Validation

### Invoices Tab
- [ ] All displayed invoices have is_paid = TRUE
- [ ] All displayed invoices have paid_date within date range
- [ ] Revenue column matches invoice.grand_total
- [ ] COGS calculation is correct
- [ ] Gross profit = Revenue - Discount - COGS
- [ ] Payment methods are displayed
- [ ] Totals row matches sum of individual rows

### Partial Payments Tab
- [ ] All displayed services have invoice_id = NULL
- [ ] All displayed services have partial_payment_amount > 0
- [ ] No cancelled services appear
- [ ] Payment percentage is calculated correctly
- [ ] COGS is proportional to payment percentage
- [ ] Gross profit = Revenue - COGS
- [ ] Totals row matches sum of individual rows

### Payment Methods Tab
- [ ] All payment methods are listed
- [ ] Transaction counts are accurate
- [ ] Amount collected matches invoice payments
- [ ] Percentages add up to 100%
- [ ] Total matches sum of all methods

---

## 🎯 Key Metrics Validation

### Revenue Reconciliation
```
Total Revenue = Materials Revenue + Services Revenue

Materials Revenue = POS Sales + Sales Orders
Services Revenue = Service Invoices + Partial Payments

Verify:
- [ ] Sum of all revenue sources matches Total Revenue
- [ ] No revenue is counted twice
- [ ] All paid invoices are included
- [ ] All partial payments (not invoiced) are included
```

### COGS Reconciliation
```
Total COGS = Materials COGS + Services COGS

Verify:
- [ ] Materials COGS uses inventory cost prices
- [ ] Services COGS includes parts + labor + other materials
- [ ] Partial payment COGS is proportional
- [ ] No COGS is counted twice
```

### Gross Profit Validation
```
Gross Profit = Net Revenue - Total COGS
Gross Margin = (Gross Profit / Net Revenue) × 100

Verify:
- [ ] Gross profit calculation is correct
- [ ] Gross margin percentage is accurate
- [ ] Separate margins for materials and services
- [ ] Combined margin is weighted average
```

### Net Profit Validation
```
Net Profit = Gross Profit - Operating Expenses
Net Margin = (Net Profit / Net Revenue) × 100

Verify:
- [ ] Operating expenses are correctly categorized
- [ ] COGS expenses are excluded from OPEX
- [ ] Net profit calculation is correct
- [ ] Net margin percentage is accurate
```

---

## 🚨 Edge Cases

### Edge Case 1: Service with Discount
```
Service: ₱100,000 quotation
Discount: ₱10,000
Partial Payment: ₱40,000
Expected: 40% recognition on ₱90,000 net
```
- [ ] Test and verify discount handling

### Edge Case 2: Service with Scrap Items
```
Service with:
- Regular items: ₱50,000 COGS
- Scrap items: ₱10,000 COGS (should be excluded)
Expected: Only ₱50,000 COGS recognized
```
- [ ] Test and verify scrap exclusion

### Edge Case 3: Service with Bundles
```
Service with:
- Individual items
- Price list bundles
Expected: COGS includes all bundle items
```
- [ ] Test and verify bundle COGS

### Edge Case 4: Service with Other Materials
```
Service with:
- Catalog items: ₱30,000 COGS
- Other materials: ₱15,000 COGS
Expected: Total COGS = ₱45,000
```
- [ ] Test and verify other materials inclusion

### Edge Case 5: Zero Quotation Service
```
Service: ₱0 quotation
Partial Payment: ₱10,000
Expected: Handle gracefully, no division by zero
```
- [ ] Test and verify error handling

---

## 📈 Performance Testing

### Large Dataset Test
- [ ] Test with 1,000+ services
- [ ] Test with 100+ partial payments
- [ ] Verify query performance (< 3 seconds)
- [ ] Check memory usage
- [ ] Verify pagination works

### Concurrent Access Test
- [ ] Multiple users accessing report simultaneously
- [ ] No data corruption
- [ ] No locking issues
- [ ] Consistent results across users

---

## 🔄 Regression Testing

### After Code Changes
- [ ] Re-run all test scenarios
- [ ] Verify no existing functionality broken
- [ ] Check all edge cases still work
- [ ] Validate debug information accuracy

### After Database Changes
- [ ] Verify migrations applied correctly
- [ ] Check data integrity
- [ ] Validate foreign key relationships
- [ ] Test with existing production data

---

## 📝 Test Results Documentation

### For Each Test Scenario
Document:
- [ ] Test date and time
- [ ] Tester name
- [ ] Environment (dev/staging/production)
- [ ] Test data used
- [ ] Expected results
- [ ] Actual results
- [ ] Pass/Fail status
- [ ] Screenshots (if applicable)
- [ ] Issues found
- [ ] Notes and observations

### Issue Tracking
For any failures:
- [ ] Create issue ticket
- [ ] Assign priority (Critical/High/Medium/Low)
- [ ] Assign to developer
- [ ] Include reproduction steps
- [ ] Attach test data
- [ ] Link to related documentation

---

## ✅ Sign-Off Checklist

### Before Production Deployment
- [ ] All test scenarios passed
- [ ] All edge cases handled
- [ ] Performance is acceptable
- [ ] Debug information is accurate
- [ ] Documentation is complete
- [ ] User training completed
- [ ] Backup plan in place
- [ ] Rollback procedure tested

### Stakeholder Approval
- [ ] Development team sign-off
- [ ] QA team sign-off
- [ ] Accounting team sign-off
- [ ] Business owner sign-off
- [ ] IT operations sign-off

---

## 🆘 Troubleshooting Guide

### Issue: Service appears in both tabs
**Check:**
1. Service invoice_id (should be NULL for partial payments)
2. Invoice is_paid status
3. Query logic in views.py
4. Debug information counts

**Fix:** Verify invoice linking is correct

### Issue: Revenue doesn't match
**Check:**
1. Date range filter
2. Invoice paid_date
3. Service service_date
4. Voided invoices excluded
5. Cancelled services excluded

**Fix:** Adjust date range or check data integrity

### Issue: COGS seems wrong
**Check:**
1. Item cost prices in catalog
2. Unit conversions
3. Scrap items excluded
4. Other materials cost vs selling price
5. Bundle item calculations

**Fix:** Review cost price data

### Issue: Debug counts don't match
**Check:**
1. Database query results
2. Filter logic
3. Exclusion criteria
4. Date range application

**Fix:** Review query logic in views.py

---

## 📚 Reference Documents

- **PARTIAL_PAYMENT_PNL_FIX.md** - Detailed fix explanation
- **PARTIAL_PAYMENT_FLOW_DIAGRAM.md** - Visual flow diagrams
- **PNL_CALCULATION_QUICK_REFERENCE.md** - Calculation formulas
- **PARTIAL_PAYMENT_FIX_SUMMARY.md** - Executive summary

---

**Testing Status:** ⏳ Pending
**Last Updated:** 2026-04-22
**Version:** 1.0
**Prepared By:** Kiro AI Assistant

---

## 📋 Test Execution Log

| Date | Tester | Scenario | Result | Notes |
|------|--------|----------|--------|-------|
| | | | | |
| | | | | |
| | | | | |

---

**Ready to test? Start with Scenario 1 and work through each test systematically!** ✅
