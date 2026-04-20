# Cashflow: Three Expense Sections Explained

## Overview

The cashflow display shows **THREE different types of expenses**, each representing a different category of cash outflow:

```
┌─────────────────────────────────────────────────────────────┐
│ 1. PROCUREMENT COSTS (Top)                                  │
│    - Buying inventory/materials from suppliers              │
│    - GRN (Goods Receipt Notes)                              │
│    - Category: PROCUREMENT                                  │
├─────────────────────────────────────────────────────────────┤
│ 2. OPERATIONAL EXPENSES (Middle)                            │
│    - Running the business (rent, utilities, salaries, etc.) │
│    - From Expense model                                     │
│    - Category: EXPENSES                                     │
├─────────────────────────────────────────────────────────────┤
│ 3. OTHER CASH OUT (Bottom)                                  │
│    - Everything else (capital, supplies, other)             │
│    - Manual cashflow entries                                │
│    - Category: SUPPLIES, CAPITAL, OTHER                     │
└─────────────────────────────────────────────────────────────┘
```

---

## Detailed Breakdown

### 1. 📦 Procurement Costs (Top Section)

**What it is:**
- Money spent on **buying inventory** and materials from suppliers
- Recorded as **GRN (Goods Receipt Notes)** when you receive goods

**Source:**
```python
expenses_procurement = Decimal('0')
grns = GoodsReceipt.objects.filter(
    status=DocumentStatus.POSTED,
    receipt_date__gte=start_date,
    receipt_date__lt=end_date,
)
for grn in grns:
    for line in grn.lines.all():
        cost = line.qty * po_line.unit_price
        expenses_procurement += cost
```

**Examples:**
- GRN-001: Bought ₱50,000 worth of products from Supplier A
- GRN-002: Bought ₱30,000 worth of materials from Supplier B

**Cashflow Category:** `PROCUREMENT`

**Display:** Shows as GRN entries with supplier names

---

### 2. 💸 Operational Expenses (Middle Section)

**What it is:**
- Money spent on **running the business** (not buying inventory)
- Day-to-day operational costs

**Source:**
```python
expenses_operational = Expense.objects.filter(
    status='APPROVED',
    date__gte=start_date,
    date__lt=end_date,
).aggregate(total=Sum('amount'))['total']
```

**Examples:**
- Employee salaries: ₱25,000
- Rent: ₱10,000
- Utilities (electricity, water): ₱5,000
- Office supplies: ₱2,000
- Marketing: ₱3,000
- Transportation: ₱1,500

**Cashflow Category:** `EXPENSES`

**Display:** Shows as expense entries with category names (from ExpenseCategory model)

**Note:** These are converted to CashFlowTransaction entries via:
- **Signal** (real-time when expense is marked PAID)
- **Sync** (batch process that recreates all expense entries)

---

### 3. 💰 Other Cash Out (Bottom Section)

**What it is:**
- All other cash outflows that don't fit into Procurement or Operational Expenses
- Manual cashflow entries you create

**Source:**
```python
expenses_other = CashFlowTransaction.objects.filter(
    status=CashFlowStatus.APPROVED,
    flow_type=CashFlowType.CASH_OUT,
    transaction_date__gte=start_date,
    transaction_date__lt=end_date,
).exclude(
    category__in=[CashFlowCategory.PROCUREMENT, CashFlowCategory.EXPENSES]
).aggregate(total=Sum('amount'))['total']
```

**Examples:**
- Capital investments: ₱100,000 (buying equipment)
- Supplies: ₱5,000 (non-inventory supplies)
- Loan repayments: ₱20,000
- Owner withdrawals: ₱15,000
- Other miscellaneous: ₱3,000

**Cashflow Categories:** `SUPPLIES`, `CAPITAL`, `OTHER`

**Display:** Shows as manual cashflow transaction entries

---

## Summary Formula

```
Total Expenses = Procurement Costs + Operational Expenses + Other Cash Out
```

**Example:**
```
Procurement Costs:      ₱80,000  (buying inventory)
Operational Expenses:   ₱46,500  (running business)
Other Cash Out:         ₱143,000 (capital, supplies, other)
─────────────────────────────────
Total Expenses:         ₱269,500
```

---

## Are They Different Types?

**YES!** They are **completely different** types of expenses:

| Section | Purpose | Source | Category |
|---------|---------|--------|----------|
| **Procurement** | Buy inventory to sell | GoodsReceipt | PROCUREMENT |
| **Operational** | Run the business | Expense model | EXPENSES |
| **Other Cash Out** | Everything else | Manual entries | SUPPLIES, CAPITAL, OTHER |

---

## Why Three Sections?

This separation helps you understand:

1. **Procurement Costs** → How much you're spending on inventory (COGS)
2. **Operational Expenses** → How much it costs to run the business
3. **Other Cash Out** → Other cash outflows (investments, etc.)

This gives you better visibility into where your money is going!

---

## Verification

To verify what's in each section, check the cashflow transaction categories:

```python
from cashflow.models import CashFlowTransaction, CashFlowCategory, CashFlowType

# Procurement
procurement = CashFlowTransaction.objects.filter(
    flow_type=CashFlowType.CASH_OUT,
    category=CashFlowCategory.PROCUREMENT
)
print(f"Procurement entries: {procurement.count()}")

# Operational Expenses
expenses = CashFlowTransaction.objects.filter(
    flow_type=CashFlowType.CASH_OUT,
    category=CashFlowCategory.EXPENSES
)
print(f"Operational expense entries: {expenses.count()}")

# Other Cash Out
other = CashFlowTransaction.objects.filter(
    flow_type=CashFlowType.CASH_OUT
).exclude(
    category__in=[CashFlowCategory.PROCUREMENT, CashFlowCategory.EXPENSES]
)
print(f"Other cash out entries: {other.count()}")
```

---

## Conclusion

The three sections are **NOT duplicates** - they represent three distinct types of cash outflows:

1. ✅ **Procurement** = Buying inventory
2. ✅ **Operational** = Running the business
3. ✅ **Other** = Everything else

Each serves a different purpose in tracking your business finances!

---

**Last Updated:** April 20, 2026  
**Documented By:** Kiro AI Assistant
