# Partial Payment Flow Diagram

## 🔄 Complete Service & Payment Lifecycle

```
                    SERVICE LIFECYCLE & P&L IMPACT
                    ==============================

┌─────────────────────────────────────────────────────────────────┐
│                     STAGE 1: SERVICE CREATION                   │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  User Action:                                                   │
│  • Create new service                                           │
│  • Set quotation: ₱75,000                                       │
│  • Add parts, labor, materials                                  │
│                                                                 │
│  Database State:                                                │
│  ┌──────────────────────────────────────┐                      │
│  │ CustomerService                      │                      │
│  ├──────────────────────────────────────┤                      │
│  │ service_number: SVC-2026-001         │                      │
│  │ quotation: 75000.00                  │                      │
│  │ status: DRAFT                        │                      │
│  │ payment_status: UNPAID               │                      │
│  │ partial_payment_amount: 0.00         │                      │
│  │ invoice: NULL                        │                      │
│  └──────────────────────────────────────┘                      │
│                                                                 │
│  P&L Impact: NONE                                               │
│  ┌──────────────────────────────────────┐                      │
│  │ ❌ Not in "Invoices" tab             │                      │
│  │ ❌ Not in "Partial Payments" tab     │                      │
│  └──────────────────────────────────────┘                      │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
                              ↓
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                  STAGE 2: PARTIAL PAYMENT RECEIVED              │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  User Action:                                                   │
│  • Customer pays ₱30,000 upfront                                │
│  • Update partial_payment_amount                                │
│  • Change payment_status to PARTIAL                             │
│                                                                 │
│  Database State:                                                │
│  ┌──────────────────────────────────────┐                      │
│  │ CustomerService                      │                      │
│  ├──────────────────────────────────────┤                      │
│  │ service_number: SVC-2026-001         │                      │
│  │ quotation: 75000.00                  │                      │
│  │ status: IN_PROGRESS                  │                      │
│  │ payment_status: PARTIAL              │                      │
│  │ partial_payment_amount: 30000.00 ✅  │                      │
│  │ invoice: NULL ✅                     │                      │
│  └──────────────────────────────────────┘                      │
│                                                                 │
│  Calculation:                                                   │
│  ┌──────────────────────────────────────┐                      │
│  │ Payment % = 30,000 / 75,000 = 40%   │                      │
│  │ Full COGS = ₱45,000                  │                      │
│  │ Proportional COGS = 45,000 × 40%    │                      │
│  │                   = ₱18,000          │                      │
│  └──────────────────────────────────────┘                      │
│                                                                 │
│  P&L Impact: PARTIAL RECOGNITION                                │
│  ┌──────────────────────────────────────┐                      │
│  │ ❌ Not in "Invoices" tab             │                      │
│  │ ✅ IN "Partial Payments" tab         │                      │
│  │    • Revenue: ₱30,000                │                      │
│  │    • COGS: ₱18,000                   │                      │
│  │    • Gross Profit: ₱12,000           │                      │
│  │    • Margin: 40%                     │                      │
│  └──────────────────────────────────────┘                      │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
                              ↓
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                   STAGE 3: SERVICE COMPLETED                    │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  User Action:                                                   │
│  • Mark service as COMPLETED                                    │
│  • Create invoice for remaining ₱45,000                         │
│  • Link invoice to service                                      │
│                                                                 │
│  Database State:                                                │
│  ┌──────────────────────────────────────┐                      │
│  │ CustomerService                      │                      │
│  ├──────────────────────────────────────┤                      │
│  │ service_number: SVC-2026-001         │                      │
│  │ quotation: 75000.00                  │                      │
│  │ status: COMPLETED ✅                 │                      │
│  │ payment_status: PARTIAL              │                      │
│  │ partial_payment_amount: 30000.00     │                      │
│  │ invoice: Invoice #12345 ✅           │                      │
│  └──────────────────────────────────────┘                      │
│                                                                 │
│  ┌──────────────────────────────────────┐                      │
│  │ Invoice #12345                       │                      │
│  ├──────────────────────────────────────┤                      │
│  │ grand_total: 45000.00                │                      │
│  │ is_paid: False ⏳                    │                      │
│  │ paid_date: NULL                      │                      │
│  └──────────────────────────────────────┘                      │
│                                                                 │
│  P&L Impact: REMOVED FROM PARTIAL                               │
│  ┌──────────────────────────────────────┐                      │
│  │ ❌ Not in "Invoices" tab             │                      │
│  │    (invoice not paid yet)            │                      │
│  │ ❌ REMOVED from "Partial Payments"   │                      │
│  │    (has invoice now)                 │                      │
│  └──────────────────────────────────────┘                      │
│                                                                 │
│  ⚠️ IMPORTANT: Service disappears from P&L until invoice paid   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
                              ↓
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                     STAGE 4: INVOICE PAID                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  User Action:                                                   │
│  • Customer pays remaining ₱45,000                              │
│  • Mark invoice as paid                                         │
│  • Set paid_date                                                │
│                                                                 │
│  Database State:                                                │
│  ┌──────────────────────────────────────┐                      │
│  │ CustomerService                      │                      │
│  ├──────────────────────────────────────┤                      │
│  │ service_number: SVC-2026-001         │                      │
│  │ quotation: 75000.00                  │                      │
│  │ status: COMPLETED                    │                      │
│  │ payment_status: PAID ✅              │                      │
│  │ partial_payment_amount: 30000.00     │                      │
│  │ invoice: Invoice #12345              │                      │
│  └──────────────────────────────────────┘                      │
│                                                                 │
│  ┌──────────────────────────────────────┐                      │
│  │ Invoice #12345                       │                      │
│  ├──────────────────────────────────────┤                      │
│  │ grand_total: 75000.00 ✅             │                      │
│  │ is_paid: True ✅                     │                      │
│  │ paid_date: 2026-04-22 ✅             │                      │
│  └──────────────────────────────────────┘                      │
│                                                                 │
│  P&L Impact: FULL RECOGNITION IN INVOICES                       │
│  ┌──────────────────────────────────────┐                      │
│  │ ✅ IN "Invoices" tab                 │                      │
│  │    • Revenue: ₱75,000 (full)         │                      │
│  │    • COGS: ₱45,000 (full)            │                      │
│  │    • Gross Profit: ₱30,000           │                      │
│  │    • Margin: 40%                     │                      │
│  │ ❌ Not in "Partial Payments" tab     │                      │
│  └──────────────────────────────────────┘                      │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🔍 Query Logic Visualization

```
                    PARTIAL PAYMENTS QUERY FLOW
                    ===========================

┌─────────────────────────────────────────────────────────────────┐
│                    ALL CUSTOMER SERVICES                        │
│                    (1,000 services total)                       │
└─────────────────────────────────────────────────────────────────┘
                              ↓
                              ↓ Filter: partial_payment_amount > 0
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│              SERVICES WITH PARTIAL PAYMENTS                     │
│                    (150 services)                               │
│                                                                 │
│  Examples:                                                      │
│  • SVC-001: ₱30,000 of ₱75,000                                  │
│  • SVC-002: ₱50,000 of ₱100,000                                 │
│  • SVC-003: ₱20,000 of ₱50,000                                  │
│  • ... (147 more)                                               │
└─────────────────────────────────────────────────────────────────┘
                              ↓
                              ↓ Filter: invoice__isnull=True
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│         SERVICES WITH PARTIAL PAYMENTS (NOT INVOICED)           │
│                    (80 services)                                │
│                                                                 │
│  Excluded (70 services):                                        │
│  • SVC-001: Has Invoice #12345 ❌                               │
│  • SVC-002: Has Invoice #12346 ❌                               │
│  • ... (68 more with invoices)                                  │
│                                                                 │
│  Remaining (80 services):                                       │
│  • SVC-003: No invoice yet ✅                                   │
│  • SVC-004: No invoice yet ✅                                   │
│  • ... (78 more without invoices)                               │
└─────────────────────────────────────────────────────────────────┘
                              ↓
                              ↓ Exclude: status=CANCELLED
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│      ACTIVE SERVICES WITH PARTIAL PAYMENTS (NOT INVOICED)       │
│                    (75 services)                                │
│                                                                 │
│  Excluded (5 services):                                         │
│  • SVC-003: Status = CANCELLED ❌                               │
│  • ... (4 more cancelled)                                       │
│                                                                 │
│  Remaining (75 services):                                       │
│  • SVC-004: Status = IN_PROGRESS ✅                             │
│  • SVC-005: Status = DRAFT ✅                                   │
│  • SVC-006: Status = COMPLETED ✅                               │
│  • ... (72 more active)                                         │
└─────────────────────────────────────────────────────────────────┘
                              ↓
                              ↓ Exclude: id in invoiced_service_ids
                              ↓ (Extra safety check)
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│    VERIFIED SERVICES WITH PARTIAL PAYMENTS (NOT INVOICED)       │
│                    (75 services)                                │
│                                                                 │
│  No additional exclusions (safety check passed)                 │
└─────────────────────────────────────────────────────────────────┘
                              ↓
                              ↓ Filter: service_date in date range
                              ↓ (e.g., April 1-30, 2026)
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│              FINAL RESULT: PARTIAL PAYMENTS TO SHOW             │
│                    (25 services)                                │
│                                                                 │
│  Excluded (50 services):                                        │
│  • SVC-004: service_date = March 15 ❌                          │
│  • SVC-005: service_date = May 10 ❌                            │
│  • ... (48 more outside date range)                             │
│                                                                 │
│  Included (25 services):                                        │
│  • SVC-006: service_date = April 5 ✅                           │
│  • SVC-007: service_date = April 12 ✅                          │
│  • SVC-008: service_date = April 20 ✅                          │
│  • ... (22 more in April)                                       │
│                                                                 │
│  These 25 services appear in "Partial Payments" tab             │
└─────────────────────────────────────────────────────────────────┘
```

---

## 💰 Revenue Recognition Timeline

```
                    REVENUE RECOGNITION OVER TIME
                    =============================

Month 1 (January)
┌─────────────────────────────────────────────────────────────────┐
│ Service Created: SVC-2026-001                                   │
│ Quotation: ₱75,000                                              │
│                                                                 │
│ P&L Impact:                                                     │
│ Revenue: ₱0                                                     │
│ COGS: ₱0                                                        │
│ Gross Profit: ₱0                                                │
└─────────────────────────────────────────────────────────────────┘

Month 2 (February)
┌─────────────────────────────────────────────────────────────────┐
│ Partial Payment Received: ₱30,000 (40%)                         │
│                                                                 │
│ P&L Impact (February):                                          │
│ Revenue: ₱30,000 ✅                                             │
│ COGS: ₱18,000 (40% of ₱45,000) ✅                               │
│ Gross Profit: ₱12,000 ✅                                        │
│                                                                 │
│ Cumulative P&L:                                                 │
│ Revenue: ₱30,000                                                │
│ COGS: ₱18,000                                                   │
│ Gross Profit: ₱12,000                                           │
└─────────────────────────────────────────────────────────────────┘

Month 3 (March)
┌─────────────────────────────────────────────────────────────────┐
│ Service Completed & Invoiced                                    │
│ Invoice Created: ₱75,000                                        │
│ Invoice Status: UNPAID                                          │
│                                                                 │
│ P&L Impact (March):                                             │
│ Revenue: ₱0 ⚠️                                                  │
│ COGS: ₱0 ⚠️                                                     │
│ Gross Profit: ₱0 ⚠️                                             │
│                                                                 │
│ Note: Service removed from "Partial Payments" but invoice       │
│       not yet paid, so not in "Invoices" either                 │
│                                                                 │
│ Cumulative P&L:                                                 │
│ Revenue: ₱30,000 (from February)                                │
│ COGS: ₱18,000 (from February)                                   │
│ Gross Profit: ₱12,000 (from February)                           │
└─────────────────────────────────────────────────────────────────┘

Month 4 (April)
┌─────────────────────────────────────────────────────────────────┐
│ Invoice Paid: ₱75,000                                           │
│                                                                 │
│ P&L Impact (April):                                             │
│ Revenue: ₱75,000 ✅                                             │
│ COGS: ₱45,000 ✅                                                │
│ Gross Profit: ₱30,000 ✅                                        │
│                                                                 │
│ Cumulative P&L:                                                 │
│ Revenue: ₱105,000 (₱30k Feb + ₱75k Apr)                         │
│ COGS: ₱63,000 (₱18k Feb + ₱45k Apr)                             │
│ Gross Profit: ₱42,000 (₱12k Feb + ₱30k Apr)                     │
│                                                                 │
│ ⚠️ ISSUE: Revenue counted twice!                                │
│    • ₱30,000 in February (partial)                              │
│    • ₱75,000 in April (full invoice)                            │
│    • Total: ₱105,000 instead of ₱75,000                         │
│                                                                 │
│ ✅ FIX: With our fix, February ₱30k is removed when invoiced    │
│    • Only ₱75,000 appears in April                              │
│    • Total: ₱75,000 (correct!)                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🎯 Double-Counting Prevention

```
                    BEFORE FIX (WRONG)
                    ==================

Service SVC-001:
├─ Quotation: ₱75,000
├─ Partial Payment: ₱30,000
└─ Invoice: #12345 (paid)

Query 1: Paid Invoices
┌──────────────────────────────────┐
│ Invoice #12345                   │
│ Revenue: ₱75,000 ✅              │
└──────────────────────────────────┘

Query 2: Partial Payments (OLD LOGIC)
┌──────────────────────────────────┐
│ SVC-001                          │
│ Partial: ₱30,000 ❌              │
│ (Still included because          │
│  partial < quotation)            │
└──────────────────────────────────┘

Total Revenue: ₱105,000 ❌ WRONG!


                    AFTER FIX (CORRECT)
                    ===================

Service SVC-001:
├─ Quotation: ₱75,000
├─ Partial Payment: ₱30,000
└─ Invoice: #12345 (paid)

Query 1: Paid Invoices
┌──────────────────────────────────┐
│ Invoice #12345                   │
│ Revenue: ₱75,000 ✅              │
└──────────────────────────────────┘

Query 2: Partial Payments (NEW LOGIC)
┌──────────────────────────────────┐
│ (Empty)                          │
│ SVC-001 excluded because         │
│ invoice is not NULL ✅           │
└──────────────────────────────────┘

Total Revenue: ₱75,000 ✅ CORRECT!
```

---

## 📊 P&L Tab Distribution

```
                    SERVICE DISTRIBUTION ACROSS TABS
                    ================================

All Services (1,000 total)
│
├─ Cancelled (50) ❌ Excluded from all tabs
│
├─ No Payments Yet (700)
│  └─ Not in any P&L tab
│
├─ Partial Payments (150)
│  │
│  ├─ With Invoice (70)
│  │  │
│  │  ├─ Invoice Paid (60)
│  │  │  └─ ✅ In "Invoices" tab
│  │  │
│  │  └─ Invoice Unpaid (10)
│  │     └─ ❌ Not in any tab (waiting for payment)
│  │
│  └─ Without Invoice (80)
│     │
│     ├─ Outside Date Range (55)
│     │  └─ ❌ Not in any tab (filtered out)
│     │
│     └─ In Date Range (25)
│        └─ ✅ In "Partial Payments" tab
│
└─ Fully Paid via Invoice (100)
   │
   ├─ Invoice Paid (90)
   │  └─ ✅ In "Invoices" tab
   │
   └─ Invoice Unpaid (10)
      └─ ❌ Not in any tab (waiting for payment)


SUMMARY:
┌────────────────────────────────────────┐
│ "Invoices" Tab: 150 services           │
│ ├─ Partial → Invoiced: 60              │
│ └─ Direct Invoiced: 90                 │
│                                        │
│ "Partial Payments" Tab: 25 services    │
│ └─ Partial, not invoiced, in range     │
│                                        │
│ Not in P&L: 825 services               │
│ ├─ Cancelled: 50                       │
│ ├─ No payments: 700                    │
│ ├─ Waiting for invoice payment: 20     │
│ └─ Outside date range: 55              │
└────────────────────────────────────────┘
```

---

**Last Updated:** 2026-04-22
**Purpose:** Visual guide for understanding partial payment flow
**Audience:** Developers, Accountants, Business Analysts
