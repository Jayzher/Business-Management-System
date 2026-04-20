# Cashflow: Fixed Procurement Duplication in Operational Expenses

## Issue

Procurement expenses were appearing in **BOTH** sections:
1. **Procurement Costs** section (from GRN)
2. **Operational Expenses** section (from Expense model)

This caused procurement costs to be counted twice!

## Root Cause

The `Expense` model has a `category` field that links to `ExpenseCategory`. Some expense categories are marked as `is_cogs=True`, which means they are procurement/COGS-related expenses.

**Before the fix:**
```python
# Operational Expenses query was getting ALL expenses
expenses_operational = Expense.objects.filter(
    status='APPROVED',
    date__gte=start_date,
    date__lt=end_date,
).aggregate(total=Sum('amount'))['total']
```

This included:
- ✅ True operational expenses (rent, salaries, utilities)
- ❌ Procurement expenses (marked as `is_cogs=True`)

## Solution

**Exclude COGS/procurement expenses** from the operational expenses calculation:

```python
# Operational Expenses (exclude COGS/procurement expenses)
expenses_operational = Expense.objects.filter(
    status='APPROVED',
    date__gte=start_date,
    date__lt=end_date,
    category__is_cogs=False,  # ← NEW: Exclude procurement expenses
).aggregate(total=Sum('amount'))['total']
```

## What Changed

**File:** `Business-Management-System/cashflow/monthly_signals.py`

**Before:**
```python
# Operational Expenses
result = Expense.objects.filter(
    status='APPROVED',
    date__gte=start_date,
    date__lt=end_date,
).aggregate(total=Sum('amount'))
expenses_operational = result['total'] or Decimal('0')
```

**After:**
```python
# Operational Expenses (exclude COGS/procurement expenses)
result = Expense.objects.filter(
    status='APPROVED',
    date__gte=start_date,
    date__lt=end_date,
    category__is_cogs=False,  # Exclude procurement/COGS expenses
).aggregate(total=Sum('amount'))
expenses_operational = result['total'] or Decimal('0')
```

## Result

Now the three expense sections are properly separated:

### 1. 📦 Procurement Costs
- **Source:** GRN (Goods Receipt Notes)
- **Includes:** Inventory purchases from suppliers
- **Example:** GRN-001, GRN-002

### 2. 💸 Operational Expenses
- **Source:** Expense model with `category.is_cogs=False`
- **Includes:** True operational costs (rent, salaries, utilities, etc.)
- **Excludes:** Procurement/COGS expenses
- **Example:** Employee Payroll, Rent, Utilities

### 3. 💰 Other Cash Out
- **Source:** Manual cashflow entries
- **Includes:** Capital, supplies, other categories
- **Example:** Equipment purchases, loan repayments

## Expense Categories

To check which expense categories are marked as COGS:

```python
from core.models import ExpenseCategory

# COGS categories (procurement-related)
cogs_categories = ExpenseCategory.objects.filter(is_cogs=True)
print("COGS/Procurement categories:")
for cat in cogs_categories:
    print(f"  - {cat.name} ({cat.code})")

# Operational categories (non-COGS)
operational_categories = ExpenseCategory.objects.filter(is_cogs=False)
print("\nOperational categories:")
for cat in operational_categories:
    print(f"  - {cat.name} ({cat.code})")
```

## Testing

To verify the fix:

1. **Check operational expenses total:**
   ```python
   from cashflow.models import MonthlyCashflowSummary
   
   summary = MonthlyCashflowSummary.objects.get(year=2026, month=4)
   print(f"Operational Expenses: ₱{summary.expenses_operational:,.2f}")
   ```

2. **Verify no procurement expenses in operational:**
   ```python
   from core.models import Expense
   from datetime import date
   
   # Check if any COGS expenses are being counted
   cogs_expenses = Expense.objects.filter(
       status='APPROVED',
       date__gte=date(2026, 4, 1),
       date__lt=date(2026, 5, 1),
       category__is_cogs=True,
   )
   print(f"COGS expenses (should NOT be in operational): {cogs_expenses.count()}")
   
   # Check operational expenses
   operational_expenses = Expense.objects.filter(
       status='APPROVED',
       date__gte=date(2026, 4, 1),
       date__lt=date(2026, 5, 1),
       category__is_cogs=False,
   )
   print(f"Operational expenses (should be in operational): {operational_expenses.count()}")
   ```

3. **Recalculate monthly summary:**
   ```bash
   # In Django shell
   from cashflow.monthly_signals import update_monthly_summary
   from django.contrib.auth import get_user_model
   
   User = get_user_model()
   user = User.objects.first()
   
   # Recalculate April 2026
   update_monthly_summary(2026, 4, user=user)
   ```

## Important Notes

1. **Expense Categories Setup:**
   - Make sure your expense categories are properly configured
   - Mark procurement-related categories as `is_cogs=True`
   - Mark operational categories as `is_cogs=False`

2. **After This Fix:**
   - Procurement costs will only appear in "Procurement Costs" section
   - Operational expenses will only include non-COGS expenses
   - No more duplication!

3. **Recalculation Required:**
   - After applying this fix, you need to recalculate monthly summaries
   - Click "Recalculate All" in the monthly dashboard
   - Or run the management command

## Conclusion

✅ **Fixed:** Procurement expenses no longer appear in operational expenses
✅ **Result:** Clean separation between procurement and operational costs
✅ **Formula:** `Total Expenses = Procurement + Operational (non-COGS) + Other`

---

**Status:** ✅ FIXED
**Last Updated:** April 20, 2026  
**Fixed By:** Kiro AI Assistant
