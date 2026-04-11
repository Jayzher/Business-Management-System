# Monthly Cashflow - Quick Start Guide

## 🚀 Getting Started (30 seconds)

### Step 1: Access Dashboard
Navigate to: **`/cashflow/monthly/`**

### Step 2: Auto-Create (if needed)
If you see "No monthly summaries":
- Click **"Auto-Create Summaries"** button
- Wait 2-3 seconds
- Done! ✅

### Step 3: View Data
- See year summary cards (Capital, Expenses, Net Profit)
- View interactive chart
- Click any month to see details

## 📊 What You'll See

### Dashboard
```
┌─────────────────────────────────────────────────┐
│  Total Capital (2024)        ₱1,500,000.00     │
│  Total Expenses (2024)       ₱800,000.00       │
│  Net Profit (2024)           ₱700,000.00       │
└─────────────────────────────────────────────────┘

[Interactive Chart showing monthly trends]

┌─────────────────────────────────────────────────┐
│ Month    │ Capital  │ Expenses │ Net Profit    │
├──────────┼──────────┼──────────┼───────────────┤
│ January  │ ₱150,000 │ ₱80,000  │ ₱70,000 (47%) │
│ February │ ₱120,000 │ ₱65,000  │ ₱55,000 (46%) │
│ ...      │ ...      │ ...      │ ...           │
└─────────────────────────────────────────────────┘
```

### Detail View
```
┌─────────────────────────────────────────────────┐
│  Capital (Sales):     ₱140,000.00              │
│  Capital (Other):     ₱10,000.00               │
│  Total Capital:       ₱150,000.00              │
│                                                 │
│  Procurement:         ₱50,000.00               │
│  Operational:         ₱25,000.00               │
│  Other Expenses:      ₱5,000.00                │
│  Total Expenses:      ₱80,000.00               │
│                                                 │
│  Net Profit:          ₱70,000.00 (47% margin)  │
└─────────────────────────────────────────────────┘

[Lists of: Sales, Procurements, Expenses, Other Transactions]
```

## 🔄 How It Updates

### Automatically (No Action Required)
When you:
- ✅ Post a POS sale
- ✅ Approve an expense
- ✅ Post a GRN
- ✅ Approve a cash flow transaction

→ Monthly summary updates **instantly**

### Manually (When Needed)
- Click **"Recalculate"** on detail page
- Click **"Recalculate All"** on dashboard

## 💡 Common Tasks

### View Current Month
```
/cashflow/monthly/2024/4/
```

### View Specific Year
```
/cashflow/monthly/?year=2024
```

### Create Missing Summaries
```
/cashflow/monthly/?auto_create=1
```

### Recalculate Everything
Click **"Recalculate All"** button on dashboard

## 🎯 Key Features

| Feature | Description |
|---------|-------------|
| **Real-Time** | Updates automatically when transactions occur |
| **Accurate** | Uses actual COGS and PO prices |
| **Visual** | Interactive charts with Chart.js |
| **Detailed** | Drill down to see all transactions |
| **Fast** | Efficient queries, instant updates |
| **Zero Config** | No setup, no commands, just works |

## 📱 Access Points

### Web Interface
- Dashboard: `/cashflow/monthly/`
- Detail: `/cashflow/monthly/<year>/<month>/`

### API (JSON)
- Chart Data: `/cashflow/monthly/api/<year>/chart-data/`
- Auto-Create: `POST /cashflow/monthly/api/<year>/<month>/auto-create/`

## 🆘 Troubleshooting

### "No data available"
→ Click **"Auto-Create Summaries"**

### Summary not updating
→ Check transaction status (must be POSTED/APPROVED)

### Wrong numbers
→ Click **"Recalculate"** button

### Need historical data
→ Visit `/cashflow/monthly/?auto_create=1`

## 📞 Need Help?

1. Check `AUTOMATED_MONTHLY_CASHFLOW.md` for detailed docs
2. Click "Recalculate" to fix inconsistencies
3. Verify transaction statuses (POSTED/APPROVED)

---

**That's it! The system is fully automated.** 🎉

Just use your application normally, and monthly summaries will always be accurate and up-to-date.
