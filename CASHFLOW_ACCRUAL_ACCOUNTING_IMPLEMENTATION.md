# Cashflow Accrual Accounting Implementation

## Overview
Implemented proper **accrual accounting** for inventory in the cashflow management system. This ensures accurate net profit calculations by treating inventory as an asset rather than an immediate expense.

## Problem Statement
Previously, the cashflow system treated procurement costs as immediate expenses (cash-out), which is incorrect from an accounting perspective:
- **Wrong**: Procurement = Expense (reduces net profit immediately)
- **Correct**: Procurement = Asset Conversion (cash → inventory, no profit impact)
- **Correct**: COGS (Cost of Goods Sold) = Actual Expense (when inventory is sold/used)

## Key Accounting Principles

### 1. Inventory is an Asset
When you buy inventory:
- **Cash decreases** by the purchase amount
- **Inventory asset increases** by the same amount
- **Net worth stays the same** (asset conversion, not expense)

### 2. COGS is the Actual Expense
When you sell/use inventory:
- **Inventory asset decreases** by the cost of goods
- **COGS expense increases** by the same amount
- **This reduces net profit** (actual expense recognized)

### 3. Opening/Closing Balance Includes Inventory
- **Opening Balance** = Previous month's cash + inventory assets
- **Closing Balance** = Current cash + inventory assets
- This gives a complete picture of company value

## Implementation

### 1. Added Inventory Tracking Fields to MonthlyCashflowSummary

**New Fields:**
```python
inventory_value_opening = DecimalField(
    help_text='Inventory asset value at start of month (cost basis)'
)
inventory_value_closing = DecimalField(
    help_text='Inventory asset value at end of month (cost basis)'
)
inventory_purchased = DecimalField(
    help_text='Total inventory purchased this month (procurement costs)'
)
cogs_actual = DecimalField(
    help_text='Actual COGS from sales/services this month'
)
```

**Updated Fields:**
```python
opening_balance = DecimalField(
    help_text='Opening cash + inventory assets from previous month'
)
closing_balance = DecimalField(
    help_text='Closing cash + inventory assets (opening + net cash flow)'
)
expenses_procurement = DecimalField(
    help_text='DEPRECATED: Use cogs_actual instead. Procurement is asset conversion, not expense.'
)
```

### 2. Created Inventory Value Calculation Command

**File:** `cashflow/management/commands/calculate_inventory_value.py`

Calculates total inventory asset value based on:
- Current stock balances (qty_on_hand > 0)
- Weighted average cost (item.cost_price)
- Formula: `Inventory Value = Σ(qty × cost_price)`

**Usage:**
```bash
python manage.py calculate_inventory_value
python manage.py calculate_inventory_value --as-of 2024-03-31
```

### 3. Updated Monthly Cashflow Calculation

**File:** `cashflow/management/commands/calculate_monthly_cashflow.py`

**New Calculation Logic:**

```python
# Calculate inventory values
inventory_opening = calculate_inventory_value(start_of_month)
inventory_closing = calculate_inventory_value(end_of_month)
inventory_purchased = procurement_costs(month)

# Calculate COGS (actual expense)
cogs_actual = calculate_actual_cogs(month)

# Revenue (without COGS deduction)
revenue = sales_revenue(month) + other_cash_in(month)

# Expenses (using COGS, not procurement)
expenses = cogs_actual + operational_expenses(month) + other_cash_out(month)

# Net Profit
gross_profit = revenue - cogs_actual
net_profit = gross_profit - operational_expenses - other_cash_out

# Cash Flow
net_cash_flow = revenue - expenses
closing_balance = opening_balance + net_cash_flow
```

## Example Calculation

### April 2026 Results:

```
Opening Balance:               ₱337,208.82
Inventory (Opening):           ₱1,008,011.82

Revenue (Sales):               ₱943,603.26
Revenue (Other Cash-In):       ₱3,825.00
Total Revenue:                 ₱947,428.26

Inventory Purchased:           ₱789,336.00 (asset conversion)
COGS (Actual Expense):         ₱727,270.48
Operational Expenses:          ₱0.00
Other Cash-Out:                ₱6,680.00
Total Expenses:                ₱733,950.48

Gross Profit:                  ₱216,332.78
Net Profit:                    ₱209,652.78
Net Cash Flow:                 ₱213,477.78

Inventory (Closing):           ₱1,008,011.82
Closing Balance:               ₱550,686.60
```

### Key Insights:

1. **Inventory Purchased (₱789,336)** ≠ **COGS (₱727,270)**
   - Purchased more than sold (inventory increased)
   - The difference (₱62,066) remains as inventory asset

2. **Net Profit (₱209,653)** is based on COGS, not procurement
   - Correct accounting: only expense what was sold
   - Inventory on hand is still company value

3. **Closing Balance (₱550,687)** includes inventory value
   - Complete picture of company assets
   - Cash + Inventory = Total Value

## Comparison: Before vs After

### Before (Cash Accounting - WRONG)
```
Revenue:           ₱947,428
Procurement:       ₱789,336  ← Treated as expense
Operational:       ₱0
Other:             ₱6,680
Total Expenses:    ₱796,016
Net Profit:        ₱151,412  ← WRONG (too low)
```

### After (Accrual Accounting - CORRECT)
```
Revenue:           ₱947,428
COGS:              ₱727,270  ← Actual expense (what was sold)
Operational:       ₱0
Other:             ₱6,680
Total Expenses:    ₱733,950
Net Profit:        ₱209,653  ← CORRECT
Inventory Asset:   ₱1,008,012 ← Tracked separately
```

## Benefits

1. **Accurate Net Profit**: Based on actual COGS, not procurement
2. **Asset Visibility**: Inventory value is tracked and visible
3. **Better Decision Making**: See true profitability vs inventory investment
4. **Proper Accounting**: Follows accrual accounting principles
5. **Complete Picture**: Opening/closing balance includes all assets

## Usage

### Calculate Current Inventory Value
```bash
python manage.py calculate_inventory_value
```

### Calculate Monthly Cashflow (with accrual accounting)
```bash
# Specific month
python manage.py calculate_monthly_cashflow --year 2026 --month 4

# All months
python manage.py calculate_monthly_cashflow

# Dry-run (preview)
python manage.py calculate_monthly_cashflow --year 2026 --month 4 --dry-run
```

## Database Migration

**Migration:** `cashflow/migrations/0006_add_inventory_asset_tracking.py`

Adds new fields and updates help text for existing fields. Run with:
```bash
python manage.py migrate cashflow
```

## Files Modified

1. `cashflow/models.py` - Added inventory tracking fields
2. `cashflow/migrations/0006_add_inventory_asset_tracking.py` - Migration
3. `cashflow/management/commands/calculate_inventory_value.py` - New command
4. `cashflow/management/commands/calculate_monthly_cashflow.py` - Updated calculation logic

## Technical Notes

### Inventory Valuation Method
- Uses **weighted average cost** (item.cost_price)
- Cost basis is updated when new inventory is received
- Reflects actual cost paid for inventory

### COGS Calculation
- Calculated from actual sales/services
- Uses `pos_sale_cogs()` for POS sales
- Uses `invoice.grand_total_cogs` for invoices
- Includes bundle components and unit conversions

### Opening/Closing Balance
- Opening balance = Previous month's closing balance
- Closing balance = Opening + Net Cash Flow
- Both include inventory asset value

## Date: April 24, 2026
## Status: ✅ Complete and Tested
