# Automated Monthly Cashflow System

## Overview

The Monthly Cashflow module is **fully automated** using Django signals. Monthly summaries are automatically created and updated in real-time whenever relevant transactions occur.

## How It Works

### 🔄 Automatic Updates

Monthly summaries are **automatically recalculated** when:

1. **POS Sale is posted** → Updates sales gross profit
2. **Invoice is paid** → Updates sales gross profit
3. **Delivery Note is posted** → Updates sales count
4. **Sales Pickup is posted** → Updates sales count
5. **Goods Receipt is posted** → Updates procurement costs
6. **Expense is approved** → Updates operational expenses
7. **Cash Flow Transaction is approved** → Updates capital/expenses
8. **Any of the above is deleted** → Recalculates the affected month

### 📊 Real-Time Calculation

When a transaction is saved:
```python
# Example: When a POS sale is posted
sale.status = SaleStatus.POSTED
sale.save()  # ← Signal automatically updates monthly summary
```

The signal handler:
1. Detects the transaction date (year/month)
2. Aggregates all transactions for that month
3. Calculates capital, expenses, and net profit
4. Updates or creates the `MonthlyCashflowSummary` record

### 🎯 Zero Configuration Required

No cron jobs, no scheduled tasks, no manual commands needed!

## Usage

### Accessing the Dashboard

Simply navigate to: `/cashflow/monthly/`

The dashboard will:
- Show existing monthly summaries
- Display an "Auto-Create" button if no data exists
- Automatically create summaries when you click "Auto-Create"

### Auto-Creation

**Method 1: Automatic (Recommended)**
- Post transactions normally (POS sales, GRNs, expenses, etc.)
- Monthly summaries are created/updated automatically
- No action required!

**Method 2: Manual Trigger**
- Visit `/cashflow/monthly/`
- Click "Auto-Create Summaries" button
- System scans for transaction data and creates summaries

**Method 3: View Detail Page**
- Navigate to `/cashflow/monthly/2024/1/` (any year/month)
- If summary doesn't exist, it's created automatically
- You see the data immediately

### Recalculation

**When to Recalculate:**
- After bulk data imports
- After correcting historical transactions
- If you suspect data inconsistency

**How to Recalculate:**
1. **Single Month**: Click "Recalculate" on detail page
2. **All Months**: Click "Recalculate All" on dashboard
3. **Programmatically**:
   ```python
   from cashflow.monthly_signals import update_monthly_summary
   update_monthly_summary(2024, 1, user=request.user)
   ```

## Technical Details

### Signal Handlers

Located in: `cashflow/monthly_signals.py`

**Registered Signals:**
- `post_save` for POSSale, Invoice, DeliveryNote, SalesPickup, GoodsReceipt, Expense, CashFlowTransaction
- `post_delete` for all above models

**Signal Flow:**
```
Transaction Saved
    ↓
Signal Triggered
    ↓
update_monthly_summary(year, month)
    ↓
Aggregate All Data
    ↓
Calculate Totals
    ↓
Update/Create Summary Record
```

### Calculation Logic

```python
# Capital (Cash In)
capital_sales = sum(sale.grand_total - sale.grand_total_cogs for sale in pos_sales)
capital_sales += sum(inv.grand_total - inv.grand_total_cogs for inv in invoices)
capital_other = sum(txn.amount for txn in cash_in_transactions)
capital_total = capital_sales + capital_other

# Expenses (Cash Out)
expenses_procurement = sum(line.qty * po_line.unit_price for grn in grns)
expenses_operational = sum(exp.amount for exp in expenses)
expenses_other = sum(txn.amount for txn in cash_out_transactions)
expenses_total = expenses_procurement + expenses_operational + expenses_other

# Net Profit
net_profit = capital_total - expenses_total
```

### Performance Considerations

**Optimizations:**
- Signals only trigger on status changes (POSTED, APPROVED)
- Uses `select_related()` and `prefetch_related()` for efficient queries
- Aggregates data in single queries (no N+1 problems)
- Updates only the affected month (not all months)

**Database Impact:**
- Minimal: 1 write per transaction (to update summary)
- Read queries are optimized with indexes
- No background jobs consuming resources

## API Endpoints

### Get Chart Data
```
GET /cashflow/monthly/api/<year>/chart-data/
```
Returns JSON for Chart.js visualization.

### Auto-Create Summary
```
POST /cashflow/monthly/api/<year>/<month>/auto-create/
```
Creates summary for specific month via AJAX.

**Response:**
```json
{
  "success": true,
  "message": "Created summary for January 2024",
  "data": {
    "capital_total": 150000.00,
    "expenses_total": 80000.00,
    "net_profit": 70000.00
  }
}
```

## Comparison: Automated vs Manual

| Feature | Automated (Current) | Manual (Old) |
|---------|-------------------|--------------|
| **Updates** | Real-time | Manual command |
| **Accuracy** | Always current | Can be stale |
| **User Action** | None required | Run command |
| **Performance** | Efficient | Batch processing |
| **Maintenance** | Zero | Regular cron jobs |
| **Data Freshness** | Instant | Delayed |

## Troubleshooting

### Summary Not Updating

**Check:**
1. Transaction status (must be POSTED/APPROVED)
2. Transaction date (must have valid year/month)
3. Signal registration (check `cashflow/apps.py`)

**Debug:**
```python
# In Django shell
from cashflow.monthly_signals import update_monthly_summary
summary = update_monthly_summary(2024, 1)
print(summary.capital_total, summary.expenses_total, summary.net_profit)
```

### Missing Summaries

**Solution:**
1. Visit `/cashflow/monthly/?auto_create=1`
2. Or click "Auto-Create Summaries" button
3. Or visit detail page for specific month

### Incorrect Calculations

**Solution:**
1. Click "Recalculate" on detail page
2. Verify source transaction data
3. Check transaction statuses

## Migration from Manual System

If you were using the management command:

**Before:**
```bash
python manage.py calculate_monthly_cashflow --year 2024
```

**After:**
- Just use the system normally
- Summaries update automatically
- No commands needed!

**One-Time Migration:**
```bash
# Optional: Recalculate all existing data
python manage.py calculate_monthly_cashflow  # Still works!
```

Then rely on automatic updates going forward.

## Best Practices

### ✅ Do's
- Let the system update automatically
- Use "Recalculate" only when needed
- Review summaries monthly for accuracy
- Check detail pages for transaction breakdowns

### ❌ Don'ts
- Don't manually edit summary records
- Don't run recalculation unnecessarily
- Don't bypass transaction posting workflows
- Don't delete summaries (they'll be recreated)

## Future Enhancements

Planned features:
- [ ] Email notifications for monthly summaries
- [ ] Budget vs actual comparison
- [ ] Forecasting based on trends
- [ ] Multi-currency support
- [ ] Department/branch breakdown
- [ ] Automated PDF reports
- [ ] Slack/Teams integration

## Support

For issues:
1. Check signal registration in `cashflow/apps.py`
2. Verify transaction statuses
3. Review Django logs for errors
4. Use "Recalculate" to fix inconsistencies

---

**Remember:** The system is fully automated. Just use your application normally, and monthly summaries will always be up-to-date! 🎉
