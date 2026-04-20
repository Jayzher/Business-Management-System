# Cashflow Operational Expenses Fix - COMPLETE

## Problem
Procurement expenses were appearing in BOTH sections:
1. **Procurement Costs** section (correct)
2. **Operational Expenses** section (incorrect - duplication)

This made it look like procurement costs were being counted twice in the cashflow.

## Root Cause
The `Expense` model has a `category` field that links to `ExpenseCategory`. The `ExpenseCategory` model has an `is_cogs` boolean field that marks whether an expense category is related to Cost of Goods Sold (procurement/inventory purchases).

The operational expenses calculation was querying ALL expenses without filtering out the COGS/procurement-related expenses.

## Solution Implemented - ALL FILES FIXED ✅

### 1. Fixed Monthly Summary Calculation (`cashflow/monthly_signals.py`)
**Line 111-116**: Added filter to exclude COGS expenses from operational expenses:

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

### 2. Fixed Monthly Detail View (`cashflow/monthly_views.py`)
**Line 156-162**: Added back the expenses query with proper filter:

```python
# Get operational expenses (exclude COGS/procurement expenses)
expenses = Expense.objects.filter(
    status='APPROVED',
    date__gte=start_date,
    date__lt=end_date,
    category__is_cogs=False,  # Only operational expenses, not procurement
).select_related('category').order_by('-date')
```

### 3. Fixed Management Command (`cashflow/management/commands/calculate_monthly_cashflow.py`)
**Line 297-304**: Updated the `_calculate_operational_expenses` method:

```python
def _calculate_operational_expenses(self, start_date, end_date):
    """Calculate operational expenses (utilities, salaries, etc.) - excludes COGS/procurement."""
    result = Expense.objects.filter(
        status='APPROVED',
        date__gte=start_date,
        date__lt=end_date,
        category__is_cogs=False,  # Exclude procurement/COGS expenses
    ).aggregate(total=Sum('amount'))
    return result['total'] or Decimal('0')
```

### 4. Fixed Cashflow List View (`cashflow/views.py`)
**Line 135-141**: Updated the expenses query:

```python
# Expenses - Operational (exclude COGS/procurement expenses)
expenses_qs = Expense.objects.filter(
    status='APPROVED',
    date__gte=start_date,
    date__lt=end_date,
    category__is_cogs=False,  # Exclude procurement/COGS expenses
).select_related('category', 'created_by')
```

## How It Works

### Expense Categories
The system uses `ExpenseCategory.is_cogs` to distinguish between:

- **COGS/Procurement Expenses** (`is_cogs=True`):
  - Raw materials purchases
  - Inventory purchases
  - Direct product costs
  - These appear in "Procurement Costs" section

- **Operational Expenses** (`is_cogs=False`):
  - Rent
  - Utilities
  - Salaries
  - Marketing
  - Office supplies
  - These appear in "Operational Expenses" section

### Cashflow Breakdown
Now the monthly cashflow correctly shows:

```
💰 CAPITAL
├── Sales Gross Profit: ₱XXX
└── Other Cash-In: ₱XXX

💸 EXPENSES
├── Procurement Costs: ₱XXX (from GoodsReceipt + COGS expenses)
├── Operational Expenses: ₱XXX (only non-COGS expenses)
└── Other Cash-Out: ₱XXX

📊 NET PROFIT = Capital - Expenses
```

## What You Need to Do

### Step 1: Verify Expense Categories
Check that your expense categories are properly configured:

1. Go to **Admin Panel** → **Core** → **Expense Categories**
2. Review each category and ensure `is_cogs` is set correctly:
   - ✅ Set `is_cogs=True` for: Raw Materials, Inventory Purchases, Product Costs
   - ✅ Set `is_cogs=False` for: Rent, Utilities, Salaries, Marketing, etc.

### Step 2: Recalculate Monthly Summaries
The fix only affects NEW calculations. To update existing monthly summaries:

1. Go to **Cashflow** → **Monthly Dashboard**
2. Click the **"Recalculate All"** button
3. Wait for the success message
4. Verify that operational expenses no longer include procurement costs

### Step 3: Verify the Fix
1. Go to **Cashflow** → **Monthly Dashboard**
2. Click **"View Details"** for any month
3. Check the **"Operational Expenses"** section
4. Verify it shows ONLY operational expenses (rent, utilities, etc.)
5. Verify procurement costs appear ONLY in the **"Procurements"** section

## Expected Results

### Before Fix
```
Procurement Costs: ₱50,000
Operational Expenses: ₱80,000  ← Includes ₱50,000 procurement (WRONG!)
Total Expenses: ₱130,000
```

### After Fix
```
Procurement Costs: ₱50,000
Operational Expenses: ₱30,000  ← Only operational expenses (CORRECT!)
Total Expenses: ₱80,000
```

## Files Modified (4 files)
1. ✅ `Business-Management-System/cashflow/monthly_signals.py` (line 111-116)
2. ✅ `Business-Management-System/cashflow/monthly_views.py` (line 156-162)
3. ✅ `Business-Management-System/cashflow/management/commands/calculate_monthly_cashflow.py` (line 297-304)
4. ✅ `Business-Management-System/cashflow/views.py` (line 135-141)

## Related Models
- `core.models.ExpenseCategory` - Has `is_cogs` field
- `core.models.Expense` - Links to ExpenseCategory
- `cashflow.models.MonthlyCashflowSummary` - Stores calculated totals

## Notes
- ✅ The fix ensures procurement expenses appear ONLY in the "Procurement Costs" section
- ✅ Operational expenses now correctly exclude COGS/procurement-related expenses
- ✅ The total expenses calculation remains accurate (no double-counting)
- ✅ Monthly summaries are automatically updated when transactions are posted
- ✅ Use "Recalculate All" to update historical data after the fix
- ✅ All 4 calculation points have been updated for consistency

## Testing Checklist
- [ ] Verify expense categories have correct `is_cogs` values
- [ ] Run "Recalculate All" on Monthly Dashboard
- [ ] Check monthly detail view shows correct operational expenses
- [ ] Verify procurement costs don't appear in operational section
- [ ] Confirm total expenses are correct (not doubled)
- [ ] Test with new expense entries to ensure fix works going forward

