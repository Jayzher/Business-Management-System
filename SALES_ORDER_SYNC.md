# Sales Order Synchronization System

## Overview

Automatic synchronization system that keeps Invoices, Delivery Notes, and Sales Pickups in sync with their parent Sales Orders using Django signals.

---

## How It Works

When a Sales Order is updated, Django signals automatically propagate changes to:

1. **Invoices** - Non-void invoices are updated with new customer info, pricing, and line items
2. **Delivery Notes** - Draft deliveries are updated with new shipping address, dates, and customer info
3. **Sales Pickups** - Draft pickups are updated with new pickup dates and customer info

---

## What Gets Synchronized

### Invoices (Non-Void Only)

| Field | Source | Notes |
|-------|--------|-------|
| customer_name | SO.customer.name | |
| customer_address | SO.customer.address | |
| subtotal | Calculated from SO lines | |
| delivery_charge | SO.delivery_charge | |
| grand_total | subtotal + delivery_charge | |
| lines | SO.lines + SO.price_list_lines | Completely recreated |

### Delivery Notes (Draft Only)

| Field | Source |
|-------|--------|
| shipping_address | SO.shipping_address |
| delivery_date | SO.delivery_date |
| customer | SO.customer |
| warehouse | SO.warehouse |

### Sales Pickups (Draft Only)

| Field | Source |
|-------|--------|
| pickup_date | SO.delivery_date |
| customer | SO.customer |
| warehouse | SO.warehouse |

---

## Business Rules

### Invoice Synchronization
- ✅ **Syncs**: All non-void invoices
- ❌ **Skips**: Void invoices (`is_void=True`)

### Delivery/Pickup Synchronization
- ✅ **Syncs**: Only DRAFT documents
- ❌ **Skips**: POSTED, APPROVED, or CANCELLED documents

### Transaction Safety
- All updates are atomic (all succeed or all fail)
- Row-level locking prevents concurrent modification issues
- Every sync operation is logged to audit trail

---

## Usage

### Automatic (Default)

Just update a Sales Order - sync happens automatically:

```python
from sales.models import SalesOrder
from decimal import Decimal

so = SalesOrder.objects.get(document_number='SO-001')
so.delivery_charge = Decimal('150.00')
so.save()  # ← Invoices, deliveries, pickups auto-update!
```

### Manual Sync Command

```bash
# Sync a specific Sales Order
python manage.py sync_sales_orders --sales-order SO-001

# Sync all Sales Orders
python manage.py sync_sales_orders --all

# Dry run (preview changes)
python manage.py sync_sales_orders --all --dry-run

# Sync only invoices
python manage.py sync_sales_orders --sales-order SO-001 --invoices-only
```

---

## Example Workflow

```
User updates Sales Order SO-001:
  - Changes customer from "ABC Corp" to "XYZ Ltd"
  - Changes delivery charge from $100 to $150

System automatically:
  ✅ Updates Invoice INV-001:
     - customer_name: "ABC Corp" → "XYZ Ltd"
     - delivery_charge: $100 → $150
     - grand_total: Recalculated
     - Lines: Recreated
  
  ✅ Updates Delivery DEL-001 (if draft):
     - customer: ABC Corp → XYZ Ltd
     - shipping_address: Updated
  
  ✅ Logs all changes to AuditLog
```

---

## Implementation Details

### Files Created

- `sales/signals.py` - Signal handlers for automatic synchronization
- `sales/apps.py` - Signal registration (modified)
- `sales/management/commands/sync_sales_orders.py` - Manual sync command
- `test_sales_order_sync.py` - Test suite

### Signal Handlers

**Main Handler:**
```python
@receiver(post_save, sender=SalesOrder)
def sync_sales_order_changes_to_related_documents(sender, instance, created, **kwargs)
```

**Helper Functions:**
- `_sync_invoices()` - Updates non-void invoices
- `_sync_deliveries()` - Updates draft delivery notes
- `_sync_pickups()` - Updates draft sales pickups

---

## Testing

### Run Test Suite

```bash
python manage.py shell < test_sales_order_sync.py
```

**Tests Include:**
- ✅ Invoice synchronization
- ✅ Delivery synchronization
- ✅ Pickup synchronization
- ✅ Posted document protection
- ✅ Void invoice protection
- ✅ Audit log verification

### Manual Test

```python
from sales.models import SalesOrder
from core.models import Invoice
from decimal import Decimal

# Get a sales order with an invoice
so = SalesOrder.objects.filter(invoices__isnull=False).first()
invoice = so.invoices.first()

print(f"Before: Invoice total = {invoice.grand_total}")

# Update the SO
so.delivery_charge = Decimal('200.00')
so.save()

# Refresh invoice from DB
invoice.refresh_from_db()
print(f"After: Invoice total = {invoice.grand_total}")
# Should reflect the new delivery charge
```

---

## Audit Trail

Every synchronization creates an `AuditLog` entry:

```python
from audit.models import AuditLog

# View recent syncs
logs = AuditLog.objects.filter(
    changes__source__icontains='Synced from Sales Order'
).order_by('-timestamp')[:10]

for log in logs:
    print(f"{log.timestamp}: {log.model_name} - {log.object_repr}")
    print(f"  Changes: {log.changes}")
```

---

## Disabling Signals (For Bulk Operations)

```python
from django.db.models.signals import post_save
from sales.models import SalesOrder
from sales.signals import sync_sales_order_changes_to_related_documents

# Disconnect
post_save.disconnect(sync_sales_order_changes_to_related_documents, sender=SalesOrder)

# Perform bulk operations
SalesOrder.objects.filter(...).update(...)

# Reconnect
post_save.connect(sync_sales_order_changes_to_related_documents, sender=SalesOrder)
```

---

## Troubleshooting

### Invoices not updating?
1. Check if invoice is void: `invoice.is_void`
2. Verify signals are registered: Check `sales/apps.py`
3. Check audit logs for errors

### Deliveries not updating?
1. Check if delivery is posted: `delivery.status`
2. Verify delivery is linked: `delivery.sales_order_id`

### Need to debug?
1. Check Django logs
2. Review audit logs: `AuditLog.objects.filter(model_name='Invoice')`
3. Run test suite: `python manage.py shell < test_sales_order_sync.py`

---

## Performance Considerations

### Optimizations Implemented

1. **Selective Updates** - Only fields that changed are updated
2. **Row-Level Locking** - Uses `select_for_update()` to prevent race conditions
3. **Bulk Operations** - All updates in a single transaction
4. **Conditional Execution** - Skips processing if no related documents exist

### Potential Issues

1. **Large Number of Related Documents** - If a SO has many invoices/deliveries, updates may take longer
2. **Concurrent Updates** - Row locking prevents race conditions but may cause brief waits
3. **Cascade Effects** - Updating invoices may trigger other signals (e.g., monthly summary updates)

---

## Common Scenarios

### Scenario 1: Change Customer
**What happens:**
- Invoice customer name/address updates
- Draft deliveries update customer
- Draft pickups update customer

### Scenario 2: Change Delivery Charge
**What happens:**
- Invoice delivery_charge updates
- Invoice grand_total recalculates
- Invoice lines recreate

### Scenario 3: Add/Remove Line Items
**What happens:**
- Invoice lines completely recreate
- Invoice totals recalculate
- Deliveries/pickups NOT affected (manual adjustment needed)

### Scenario 4: Update Posted Delivery
**What happens:**
- Nothing! Posted deliveries don't sync (by design)

---

**Version:** 1.0  
**Status:** Production Ready  
**Created:** 2026-05-30
