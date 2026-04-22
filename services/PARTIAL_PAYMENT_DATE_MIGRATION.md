# Adding Partial Payment Date Field - Migration Guide

## Overview
This guide explains how to add a `partial_payment_date` field to the `CustomerService` model to improve date-based filtering accuracy in financial reports.

---

## Why This Field Is Needed

### Current Problem
- Partial payments are filtered by `service_date` (when service was scheduled)
- This doesn't reflect when the payment was actually received
- Results in inaccurate period-based P&L reports

### Example Issue
```
Service scheduled: January 15, 2026
Partial payment received: February 10, 2026
Current behavior: Shows in January report ❌
Desired behavior: Shows in February report ✅
```

---

## Implementation Steps

### Step 1: Update the Model

Edit `Business-Management-System/services/models.py`:

```python
class CustomerService(models.Model):
    # ... existing fields ...
    
    partial_payment_amount = models.DecimalField(
        max_digits=15, decimal_places=2,
        null=True, blank=True, default=Decimal('0'),
        help_text='Amount already paid by the customer when payment status is Partially Paid.',
    )
    
    # NEW FIELD
    partial_payment_date = models.DateField(
        null=True, blank=True,
        help_text='Date when the partial payment was received (for accurate period reporting)',
    )
    
    partial_payment_method = models.CharField(
        max_length=20,
        choices=PaymentMethod.choices,  # Import from core.models
        null=True, blank=True,
        help_text='Payment method used for partial payment',
    )
    
    partial_payment_notes = models.TextField(
        blank=True, default='',
        help_text='Notes about the partial payment',
    )
    
    # ... rest of fields ...
```

### Step 2: Create Migration

```bash
cd Business-Management-System
python manage.py makemigrations services -n add_partial_payment_tracking
```

Expected migration file:
```python
# services/migrations/000X_add_partial_payment_tracking.py
from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [
        ('services', '000X_previous_migration'),
    ]

    operations = [
        migrations.AddField(
            model_name='customerservice',
            name='partial_payment_date',
            field=models.DateField(
                blank=True, 
                null=True,
                help_text='Date when the partial payment was received (for accurate period reporting)'
            ),
        ),
        migrations.AddField(
            model_name='customerservice',
            name='partial_payment_method',
            field=models.CharField(
                blank=True,
                max_length=20,
                null=True,
                help_text='Payment method used for partial payment'
            ),
        ),
        migrations.AddField(
            model_name='customerservice',
            name='partial_payment_notes',
            field=models.TextField(
                blank=True,
                default='',
                help_text='Notes about the partial payment'
            ),
        ),
    ]
```

### Step 3: Backfill Existing Data (Optional)

Create a data migration to set `partial_payment_date` for existing services:

```bash
python manage.py makemigrations services --empty -n backfill_partial_payment_dates
```

Edit the migration:
```python
# services/migrations/000X_backfill_partial_payment_dates.py
from django.db import migrations

def backfill_payment_dates(apps, schema_editor):
    """
    Set partial_payment_date to service_date for existing services with partial payments.
    This is an approximation - manual review may be needed for accuracy.
    """
    CustomerService = apps.get_model('services', 'CustomerService')
    
    services_with_partial = CustomerService.objects.filter(
        partial_payment_amount__gt=0,
        partial_payment_date__isnull=True
    )
    
    count = 0
    for service in services_with_partial:
        # Use service_date as best guess
        service.partial_payment_date = service.service_date
        service.save(update_fields=['partial_payment_date'])
        count += 1
    
    print(f"Backfilled {count} services with partial_payment_date")

def reverse_backfill(apps, schema_editor):
    """Reverse the backfill by clearing the dates."""
    CustomerService = apps.get_model('services', 'CustomerService')
    CustomerService.objects.filter(
        partial_payment_date__isnull=False
    ).update(partial_payment_date=None)

class Migration(migrations.Migration):
    dependencies = [
        ('services', '000X_add_partial_payment_tracking'),
    ]

    operations = [
        migrations.RunPython(backfill_payment_dates, reverse_backfill),
    ]
```

### Step 4: Run Migrations

```bash
python manage.py migrate services
```

---

## Update Views and Forms

### Update Service Form

Edit `Business-Management-System/services/forms.py`:

```python
class CustomerServiceForm(forms.ModelForm):
    class Meta:
        model = CustomerService
        fields = [
            'service_number',
            'service_name',
            'customer_name',
            'service_date',
            'address',
            'notes',
            'status',
            'payment_status',
            'partial_payment_amount',
            'partial_payment_date',      # NEW
            'partial_payment_method',    # NEW
            'partial_payment_notes',     # NEW
            'quotation',
            'discount_type',
            'discount_value',
            'warehouse',
        ]
        widgets = {
            'service_date': forms.DateInput(attrs={'type': 'date'}),
            'partial_payment_date': forms.DateInput(attrs={'type': 'date'}),  # NEW
            'notes': forms.Textarea(attrs={'rows': 3}),
            'partial_payment_notes': forms.Textarea(attrs={'rows': 2}),  # NEW
        }
```

### Update Financial Statement View

Edit `Business-Management-System/reports/views.py`:

```python
# Change the date filter from service_date to partial_payment_date
if date_from:
    partial_services_qs = partial_services_qs.filter(
        partial_payment_date__gte=date_from  # Changed from service_date
    )
if date_to:
    partial_services_qs = partial_services_qs.filter(
        partial_payment_date__lte=date_to  # Changed from service_date
    )

# Also add a fallback for services without partial_payment_date
# (for backward compatibility during transition period)
partial_services_qs = partial_services_qs.filter(
    Q(partial_payment_date__gte=date_from) | 
    Q(partial_payment_date__isnull=True, service_date__gte=date_from)
)
```

---

## Update Templates

### Service Detail/Edit Template

Add fields to display partial payment information:

```html
<!-- In service detail/edit form -->
<div class="row">
  <div class="col-md-4">
    <div class="form-group">
      <label>Partial Payment Amount</label>
      <input type="number" name="partial_payment_amount" 
             class="form-control" step="0.01">
    </div>
  </div>
  <div class="col-md-4">
    <div class="form-group">
      <label>Payment Date</label>
      <input type="date" name="partial_payment_date" 
             class="form-control">
    </div>
  </div>
  <div class="col-md-4">
    <div class="form-group">
      <label>Payment Method</label>
      <select name="partial_payment_method" class="form-control">
        <option value="">-- Select --</option>
        <option value="CASH">Cash</option>
        <option value="BANK_TRANSFER">Bank Transfer</option>
        <option value="CHECK">Check</option>
        <option value="GCASH">GCash</option>
        <option value="CREDIT_CARD">Credit Card</option>
      </select>
    </div>
  </div>
</div>
<div class="form-group">
  <label>Payment Notes</label>
  <textarea name="partial_payment_notes" class="form-control" rows="2"></textarea>
</div>
```

---

## Update Admin Interface

Edit `Business-Management-System/services/admin.py`:

```python
@admin.register(CustomerService)
class CustomerServiceAdmin(admin.ModelAdmin):
    list_display = [
        'service_number',
        'service_name',
        'customer_name',
        'service_date',
        'status',
        'payment_status',
        'partial_payment_amount',
        'partial_payment_date',  # NEW
    ]
    
    list_filter = [
        'status',
        'payment_status',
        'service_date',
        'partial_payment_date',  # NEW
    ]
    
    fieldsets = (
        ('Service Information', {
            'fields': (
                'service_number',
                'service_name',
                'customer_name',
                'service_date',
                'completion_date',
                'address',
                'notes',
            )
        }),
        ('Status', {
            'fields': ('status', 'payment_status')
        }),
        ('Payment Information', {
            'fields': (
                'quotation',
                'discount_type',
                'discount_value',
                'partial_payment_amount',
                'partial_payment_date',      # NEW
                'partial_payment_method',    # NEW
                'partial_payment_notes',     # NEW
            )
        }),
        # ... rest of fieldsets ...
    )
```

---

## Testing Plan

### Test Case 1: New Service with Partial Payment
1. Create new service with ₱100,000 quotation
2. Set partial_payment_amount = ₱40,000
3. Set partial_payment_date = today
4. Set partial_payment_method = CASH
5. Run financial statement for current month
6. Verify service appears in "Partial Payments" tab
7. Verify date filter works correctly

### Test Case 2: Existing Service (Backfilled)
1. Check existing service with partial payment
2. Verify partial_payment_date was set to service_date
3. Manually update partial_payment_date if needed
4. Verify report shows correct period

### Test Case 3: Service Without Partial Payment Date
1. Create service with partial payment but no date
2. Verify fallback to service_date works
3. Add partial_payment_date
4. Verify report updates correctly

---

## Rollback Plan

If issues arise, you can rollback:

```bash
# Rollback the migrations
python manage.py migrate services 000X_previous_migration

# Or manually remove the fields
python manage.py dbshell
```

```sql
-- SQLite
ALTER TABLE services_customerservice DROP COLUMN partial_payment_date;
ALTER TABLE services_customerservice DROP COLUMN partial_payment_method;
ALTER TABLE services_customerservice DROP COLUMN partial_payment_notes;
```

---

## Future Enhancements

### Multiple Partial Payments
Consider creating a separate model for tracking multiple payments:

```python
class ServicePayment(models.Model):
    service = models.ForeignKey(
        CustomerService, 
        on_delete=models.CASCADE, 
        related_name='payment_records'
    )
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    payment_date = models.DateField()
    payment_method = models.CharField(max_length=20, choices=PaymentMethod.choices)
    reference_number = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-payment_date']
    
    def __str__(self):
        return f"{self.service.service_number} - ₱{self.amount} on {self.payment_date}"
```

This would allow:
- Multiple partial payments per service
- Better audit trail
- More accurate period reporting
- Payment reconciliation

---

## Summary

### Benefits of This Change
✅ Accurate period-based reporting
✅ Better cash flow tracking
✅ Improved audit trail
✅ More detailed payment information
✅ Backward compatible (with fallback)

### Effort Required
- Model changes: 10 minutes
- Migrations: 5 minutes
- Form updates: 15 minutes
- View updates: 20 minutes
- Template updates: 20 minutes
- Testing: 30 minutes
- **Total: ~1.5 hours**

### Risk Level
🟢 **Low Risk**
- Non-breaking change (nullable fields)
- Backward compatible
- Easy to rollback
- No data loss risk

---

**Recommendation:** Implement this change in the next development cycle to improve financial reporting accuracy.

**Last Updated:** 2026-04-22
