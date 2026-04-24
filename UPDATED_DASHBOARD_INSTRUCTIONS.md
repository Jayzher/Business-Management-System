# Updated Financial Dashboard - Instructions

## What Was Changed

### 1. Updated Monthly Dashboard Template
**File:** `cashflow/templates/cashflow/monthly_dashboard.html`

**Changes:**
- ✅ Replaced old fields (capital_total, expenses_total) with new financial metrics
- ✅ Added 8 KPI cards showing:
  - Revenue (Accrual)
  - Gross Profit
  - Net Profit
  - Cash Flow
  - Collection Rate
  - Accounts Receivable
  - Inventory Value
  - Gross Margin
- ✅ Updated table to show: Revenue, COGS, Gross Profit, Net Profit, Cash Flow, Margin
- ✅ Updated chart to show 4 lines: Revenue, Gross Profit, Net Profit, Cash Flow

### 2. Updated Monthly Views
**File:** `cashflow/monthly_views.py`

**Changes:**
- ✅ Updated year_totals aggregation to use new fields
- ✅ Updated chart_data to include new metrics
- ✅ Added proper JSON serialization for chart data

## How to See the Changes

### Step 1: Calculate Financial Statements

You need to run the new calculation command to populate the new fields:

```bash
# Navigate to project directory
cd Business-Management-System

# Calculate for April 2026 (or your current month)
python manage.py calculate_financial_statements --year 2026 --month 4

# Or calculate for the entire year
python manage.py calculate_financial_statements --year 2026
```

This command will:
- Calculate revenue (accrual basis)
- Calculate COGS (actual expense)
- Calculate gross profit and margin
- Track cash flow (actual cash movement)
- Track accounts receivable
- Track inventory value
- Calculate performance metrics (collection rate, DSO, inventory turnover)

### Step 2: Restart Django Server

If your server is running, restart it to clear any cached templates:

```bash
# Stop the server (Ctrl+C)
# Then start it again
python manage.py runserver
```

### Step 3: View the Dashboard

Navigate to: `http://127.0.0.1:8000/cashflow/monthly/`

You should now see:
- 8 KPI cards at the top with all new metrics
- Updated table with Revenue, COGS, Gross Profit, Net Profit, Cash Flow columns
- Updated chart showing 4 lines (Revenue, Gross Profit, Net Profit, Cash Flow)

## Expected Results (April 2026 Example)

Based on the calculation command output, you should see:

### KPI Cards:
- **Revenue:** ₱943,603.26
- **Gross Profit:** ₱216,332.78
- **Net Profit:** ₱209,652.78
- **Cash Flow:** ₱97,731.26
- **Collection Rate:** 95.6%
- **Accounts Receivable:** ₱9,790.00
- **Inventory Value:** ₱1,008,011.82
- **Gross Margin:** 22.9%

### Table Columns:
- Revenue: ₱943,603.26
- COGS: ₱727,270.48
- Gross Profit: ₱216,332.78
- Net Profit: ₱209,652.78
- Cash Flow: ₱97,731.26
- Margin: 22.9%

### Chart:
- Blue line: Revenue trend
- Green line: Gross Profit trend
- Purple line: Net Profit trend
- Yellow dashed line: Cash Flow trend

## Troubleshooting

### Issue: Template Error "base.html not found"

**Solution:**
1. Clear Python cache:
   ```bash
   Remove-Item -Recurse -Force cashflow/__pycache__
   ```

2. Restart Django server:
   ```bash
   python manage.py runserver
   ```

### Issue: All values show 0.00

**Solution:**
You need to run the calculation command first:
```bash
python manage.py calculate_financial_statements --year 2026 --month 4
```

### Issue: Old fields still showing

**Solution:**
1. Make sure you saved all files
2. Restart the Django server
3. Hard refresh the browser (Ctrl+Shift+R or Ctrl+F5)

## Key Differences: Old vs New

### Old Dashboard:
- Capital Total (Sales + Other Cash-In)
- Expenses Total (Procurement + Operational + Other)
- Net Profit (Capital - Expenses) ❌ WRONG

### New Dashboard:
- Revenue (Accrual basis - what was invoiced)
- COGS (Actual expense - what was sold/used)
- Gross Profit (Revenue - COGS) ✅ CORRECT
- Net Profit (Gross Profit - Operating Expenses) ✅ CORRECT
- Cash Flow (Actual cash in - cash out) ✅ SEPARATE

## Why This Is Better

1. **Accurate Profit Calculation**
   - Old: Treated procurement as expense (wrong)
   - New: Uses COGS as expense (correct)

2. **Separate Cash vs Accrual**
   - Old: Mixed concepts
   - New: Clear separation - Cash Flow vs P&L

3. **Better Visibility**
   - Old: 3 metrics
   - New: 8 comprehensive metrics

4. **Performance Tracking**
   - Old: Only profit margin
   - New: Collection rate, DSO, inventory turnover, gross margin

## Next Steps

After verifying the dashboard works:

1. **Create Additional Views** (Optional)
   - Financial Dashboard (`/cashflow/financial/`)
   - Cash Flow Statement (`/cashflow/financial/cash-flow/2026/4/`)
   - P&L Statement (`/cashflow/financial/profit-loss/2026/4/`)
   - Balance Sheet (`/cashflow/financial/balance-sheet/2026/4/`)

2. **Export Features** (Future)
   - PDF export
   - Excel export
   - Email reports

3. **Advanced Analytics** (Future)
   - Trend analysis
   - Forecasting
   - Budget vs Actual

## Date: April 24, 2026
## Status: ✅ Dashboard Updated - Ready to Test

