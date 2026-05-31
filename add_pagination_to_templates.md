# Template Update Guide - Adding Pagination

## Quick Reference

Add this line at the bottom of each table (before closing `</div>` or `</card-body>`):

```django
{% include "theme/partials/pagination.html" with page_obj=VARIABLE_NAME items_name="ITEM_TYPE" %}
```

## Templates to Update

### 1. Invoice List
**File**: `templates/core/invoice_list.html`
**Variable**: `invoices`
**Add**:
```django
{% include "theme/partials/pagination.html" with page_obj=invoices items_name="invoices" %}
```

### 2. Expense List
**File**: `templates/core/expense_list.html`
**Variable**: `expenses`
**Add**:
```django
{% include "theme/partials/pagination.html" with page_obj=expenses items_name="expenses" %}
```

### 3. Supply Movement List
**File**: `templates/core/supply_movement_list.html`
**Variable**: `movements`
**Add**:
```django
{% include "theme/partials/pagination.html" with page_obj=movements items_name="movements" %}
```

### 4. Stock Movement Report
**File**: `templates/reports/stock_movement.html`
**Variable**: `moves`
**Add**:
```django
{% include "theme/partials/pagination.html" with page_obj=moves items_name="stock moves" %}
```

### 5. Stock Move List
**File**: `templates/inventory/stock_move_list.html`
**Variable**: `moves`
**Add**:
```django
{% include "theme/partials/pagination.html" with page_obj=moves items_name="stock moves" %}
```

### 6. POS Shift List
**File**: `templates/pos/shift_list.html`
**Variable**: `shifts`
**Add**:
```django
{% include "theme/partials/pagination.html" with page_obj=shifts items_name="shifts" %}
```

### 7. POS Receipt List
**File**: `templates/pos/receipt_list.html`
**Variable**: `sales`
**Add**:
```django
{% include "theme/partials/pagination.html" with page_obj=sales items_name="receipts" %}
```

### 8. Cash Flow Log List
**File**: `templates/cashflow/log_list.html`
**Variable**: `logs`
**Add**:
```django
{% include "theme/partials/pagination.html" with page_obj=logs items_name="log entries" %}
```

### 9. QR Code Tag List
**File**: `templates/qr/qr_list.html`
**Variable**: `tags`
**Add**:
```django
{% include "theme/partials/pagination.html" with page_obj=tags items_name="QR tags" %}
```

### 10. Warehouse Detail - Stock Balances
**File**: `templates/warehouses/warehouse_detail.html`
**Variable**: `balances`
**Add**:
```django
{% include "theme/partials/pagination.html" with page_obj=balances items_name="stock balances" %}
```

### 11. Service Invoice List
**File**: `templates/services/service_invoice_list.html`
**Variable**: `invoices`
**Add**:
```django
{% include "theme/partials/pagination.html" with page_obj=invoices items_name="service invoices" %}
```

## Typical Placement

### Option 1: After table, inside card-body
```django
<div class="card-body table-responsive p-0">
  <table class="table table-hover">
    <!-- table content -->
  </table>
</div>
<div class="card-footer">
  {% include "theme/partials/pagination.html" with page_obj=items items_name="items" %}
</div>
```

### Option 2: After table, before closing div
```django
<div class="card-body">
  <table class="table table-hover">
    <!-- table content -->
  </table>
  
  {% include "theme/partials/pagination.html" with page_obj=items items_name="items" %}
</div>
```

### Option 3: In a separate section
```django
</table>
</div>

<div class="card-footer clearfix">
  {% include "theme/partials/pagination.html" with page_obj=items items_name="items" %}
</div>
```

## Testing After Update

For each template:
1. Navigate to the page
2. Verify pagination controls appear at bottom
3. Click "Next" - should go to page 2
4. Click "Previous" - should go back to page 1
5. Click a page number - should jump to that page
6. Apply a filter - pagination should reset to page 1
7. Change pages with filter active - filter should remain

## Common Issues

### Issue: Pagination not showing
- Check if there are more than 100 items (or 50 for shifts)
- Verify the variable name matches between view and template

### Issue: Filters reset when changing pages
- This should NOT happen - pagination preserves filters
- If it does, check the pagination template is correct

### Issue: Styling looks wrong
- Verify Bootstrap CSS is loaded in base template
- Check for CSS conflicts

## Automation Script (Optional)

If you want to automate adding pagination to all templates, you can use this Python script:

```python
import os
import re

templates = [
    ('templates/core/invoice_list.html', 'invoices', 'invoices'),
    ('templates/core/expense_list.html', 'expenses', 'expenses'),
    ('templates/core/supply_movement_list.html', 'movements', 'movements'),
    ('templates/reports/stock_movement.html', 'moves', 'stock moves'),
    ('templates/inventory/stock_move_list.html', 'moves', 'stock moves'),
    ('templates/pos/shift_list.html', 'shifts', 'shifts'),
    ('templates/pos/receipt_list.html', 'sales', 'receipts'),
    ('templates/cashflow/log_list.html', 'logs', 'log entries'),
    ('templates/qr/qr_list.html', 'tags', 'QR tags'),
    ('templates/warehouses/warehouse_detail.html', 'balances', 'stock balances'),
    ('templates/services/service_invoice_list.html', 'invoices', 'service invoices'),
]

for template_path, var_name, items_name in templates:
    if os.path.exists(template_path):
        with open(template_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Add pagination before {% endblock %}
        pagination_line = f'{{% include "theme/partials/pagination.html" with page_obj={var_name} items_name="{items_name}" %}}'
        
        if pagination_line not in content:
            # Find the last </table> or </div> before {% endblock %}
            # Add pagination after it
            print(f"TODO: Manually add pagination to {template_path}")
        else:
            print(f"✓ Pagination already in {template_path}")
    else:
        print(f"✗ File not found: {template_path}")
```

## Summary

- **11 templates** need pagination added
- **Same pattern** for all: `{% include "theme/partials/pagination.html" with page_obj=VAR items_name="NAME" %}`
- **Place at bottom** of table or in card footer
- **Test each page** after updating
