# Monthly Cashflow Recording Module

## Overview

The Monthly Cashflow Recording module provides comprehensive financial tracking and reporting by aggregating capital, expenses, and net profit on a monthly basis.

## Features

### 1. **Accurate Calculations**
- **Capital (Cash In)**:
  - Gross Profit from Sales (Revenue - COGS)
  - Other Cash-In transactions (investments, capital injections)
  
- **Expenses (Cash Out)**:
  - Procurement costs from posted GRNs
  - Operational expenses (utilities, salaries, etc.)
  - Other cash-out transactions

- **Net Profit**: Capital - Expenses

### 2. **Data Sources**
The module aggregates data from:
- **POSSale**: Point-of-sale transactions with gross profit calculation
- **Invoice**: Sales invoices with COGS tracking
- **GoodsReceipt**: Procurement costs from purchase orders
- **Expense**: Operational expenses
- **CashFlowTransaction**: Manual cash-in/out entries

### 3. **Modern UI/UX**
- **Dashboard View**: 
  - Year-at-a-glance summary cards
  - Interactive line chart showing monthly trends
  - Detailed monthly breakdown table
  - Profit margin indicators
  
- **Detail View**:
  - Comprehensive breakdown by category
  - Transaction lists for sales, procurements, expenses
  - Visual indicators for positive/negative values
  - Quick recalculation button

## Usage

### Initial Setup

1. **Run Migration**:
   ```bash
   python manage.py migrate cashflow
   ```

2. **Calculate Monthly Summaries**:
   ```bash
   # Calculate all months
   python manage.py calculate_monthly_cashflow
   
   # Calculate specific year
   python manage.py calculate_monthly_cashflow --year 2024
   
   # Calculate specific month
   python manage.py calculate_monthly_cashflow --year 2024 --month 3
   
   # Dry-run (preview without saving)
   python manage.py calculate_monthly_cashflow --dry-run
   ```

### Accessing the Dashboard

Navigate to: `/cashflow/monthly/`

### Recalculation

- **From Dashboard**: Click "Recalculate All" button
- **From Detail View**: Click "Recalculate" button for specific month
- **Via Command**: Run the management command (recommended for bulk updates)

## Calculation Logic

### Capital (Sales Gross Profit)
```python
gross_profit = grand_total - grand_total_cogs
```
- Aggregates from all posted POS sales and paid invoices
- Uses actual COGS tracked at transaction time

### Procurement Costs
```python
cost = qty * unit_price (from PO line)
```
- Sums all posted GRN lines
- Uses purchase order unit prices for accurate costing

### Net Profit
```python
net_profit = capital_total - expenses_total
```

### Profit Margin
```python
profit_margin = (net_profit / capital_total) * 100
```

## API Endpoints

- `GET /cashflow/monthly/` - Dashboard view
- `GET /cashflow/monthly/<year>/<month>/` - Detail view
- `POST /cashflow/monthly/<year>/<month>/recalculate/` - Recalculate month
- `POST /cashflow/monthly/recalculate-all/` - Recalculate all months
- `GET /cashflow/monthly/api/<year>/chart-data/` - JSON chart data

## Database Schema

### MonthlyCashflowSummary

| Field | Type | Description |
|-------|------|-------------|
| year | Integer | Year (e.g., 2024) |
| month | Integer | Month (1-12) |
| capital_sales | Decimal | Gross profit from sales |
| capital_other | Decimal | Other cash-in |
| capital_total | Decimal | Total capital |
| expenses_procurement | Decimal | Procurement costs |
| expenses_operational | Decimal | Operational expenses |
| expenses_other | Decimal | Other cash-out |
| expenses_total | Decimal | Total expenses |
| net_profit | Decimal | Net profit |
| sales_count | Integer | Number of sales |
| procurement_count | Integer | Number of procurements |
| expense_count | Integer | Number of expenses |
| calculated_at | DateTime | Last calculation time |

## Best Practices

1. **Regular Recalculation**: Run monthly after closing books
2. **Data Validation**: Review detail view to verify calculations
3. **Backup**: Always backup before bulk recalculations
4. **Dry-Run First**: Use `--dry-run` flag to preview changes
5. **Audit Trail**: Check `calculated_at` timestamp to track updates

## Troubleshooting

### Missing Data
- Ensure all transactions are properly posted
- Check that COGS is calculated for sales
- Verify GRNs are linked to purchase orders

### Incorrect Calculations
- Run recalculation for affected months
- Check source transaction dates
- Verify transaction statuses (POSTED, APPROVED)

### Performance
- Use `--year` flag to limit calculation scope
- Run during off-peak hours for large datasets
- Consider database indexing on date fields

## Future Enhancements

- Export to Excel/PDF
- Budget vs Actual comparison
- Forecasting based on historical trends
- Multi-currency support
- Department/branch breakdown
- Cash flow projections
