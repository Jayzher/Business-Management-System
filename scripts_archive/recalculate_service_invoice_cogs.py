#!/usr/bin/env python
"""
Recalculate COGS for existing service invoices after the unit fix.

This script updates service invoices that were created before the
procurement unit fix was applied.
"""

import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'inventory_system.settings')
django.setup()

from decimal import Decimal
from invoices.models import Invoice
from core.cogs import compute_invoice_cogs
from django.db.models import Q

def main():
    print("=" * 80)
    print("RECALCULATE SERVICE INVOICE COGS")
    print("=" * 80)
    
    # Find service invoices (those without pos_sale or sales_order)
    service_invoices = Invoice.objects.filter(
        Q(pos_sale__isnull=True) & Q(sales_order__isnull=True)
    ).exclude(
        status='VOID'
    ).select_related(
        'customer'
    ).prefetch_related(
        'customer_services__lines__item',
        'customer_services__lines__unit',
    )
    
    total_count = service_invoices.count()
    
    if total_count == 0:
        print("\nNo service invoices found.")
        return
    
    print(f"\nFound {total_count} service invoice(s)")
    
    # Show invoices with negative profit
    print("\n" + "=" * 80)
    print("INVOICES WITH NEGATIVE PROFIT")
    print("=" * 80)
    
    negative_invoices = []
    
    for inv in service_invoices:
        if inv.grand_total_cogs > inv.grand_total:
            profit = inv.grand_total - inv.grand_total_cogs
            negative_invoices.append({
                'invoice': inv,
                'old_cogs': inv.grand_total_cogs,
                'profit': profit,
            })
    
    if not negative_invoices:
        print("\n✓ No invoices with negative profit found!")
        return
    
    print(f"\nFound {len(negative_invoices)} invoice(s) with negative profit:")
    
    for item in negative_invoices:
        inv = item['invoice']
        print(f"\n  Invoice: {inv.invoice_number}")
        print(f"  Customer: {inv.customer.name if inv.customer else 'N/A'}")
        print(f"  Date: {inv.invoice_date}")
        print(f"  Total: {inv.grand_total}")
        print(f"  Current COGS: {item['old_cogs']}")
        print(f"  Current Profit: {item['profit']}")
        
        # Calculate what the new COGS would be
        try:
            new_cogs = compute_invoice_cogs(inv)
            new_profit = inv.grand_total - new_cogs
            
            print(f"  → New COGS: {new_cogs}")
            print(f"  → New Profit: {new_profit}")
            
            if new_profit > item['profit']:
                print(f"  ✓ Improvement: +{new_profit - item['profit']:.2f}")
            
            item['new_cogs'] = new_cogs
            item['new_profit'] = new_profit
            
        except Exception as e:
            print(f"  ✗ Error calculating new COGS: {e}")
            item['new_cogs'] = None
    
    # Ask for confirmation
    print("\n" + "=" * 80)
    response = input(f"\nRecalculate COGS for these {len(negative_invoices)} invoice(s)? (yes/no): ").strip().lower()
    
    if response != 'yes':
        print("\nCancelled. No changes made.")
        return
    
    # Update invoices
    print("\n" + "=" * 80)
    print("UPDATING INVOICES")
    print("=" * 80)
    
    updated_count = 0
    error_count = 0
    
    for item in negative_invoices:
        inv = item['invoice']
        
        if item.get('new_cogs') is None:
            print(f"\n✗ Skipping {inv.invoice_number} (calculation error)")
            error_count += 1
            continue
        
        try:
            old_cogs = inv.grand_total_cogs
            inv.grand_total_cogs = item['new_cogs']
            inv.save(update_fields=['grand_total_cogs', 'updated_at'])
            
            print(f"\n✓ Updated {inv.invoice_number}")
            print(f"  COGS: {old_cogs} → {item['new_cogs']}")
            print(f"  Profit: {item['profit']} → {item['new_profit']}")
            
            updated_count += 1
            
        except Exception as e:
            print(f"\n✗ Error updating {inv.invoice_number}: {e}")
            error_count += 1
    
    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"\nTotal invoices processed: {len(negative_invoices)}")
    print(f"Successfully updated: {updated_count}")
    print(f"Errors: {error_count}")
    
    if updated_count > 0:
        print("\n✓ COGS recalculation complete!")
        print("\nNote: This only updates the COGS field. The invoice line items")
        print("and customer charges remain unchanged (as they should).")

if __name__ == '__main__':
    main()
