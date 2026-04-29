#!/usr/bin/env python
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from procurement.models import GoodsReceipt, GoodsReceiptLine
from django.db.models import Q

# Find GRNs with items that have zero cost prices
grns_with_zero_costs = []
total_zero_cost_lines = 0

for grn in GoodsReceipt.objects.all():
    # Find lines where the item has zero cost_price
    zero_cost_lines = []
    for line in grn.lines.all():
        if line.item.cost_price == 0:
            zero_cost_lines.append(line)
    
    if zero_cost_lines:
        grns_with_zero_costs.append({
            'grn': grn,
            'zero_cost_lines': zero_cost_lines,
            'total_lines': grn.lines.count()
        })
        total_zero_cost_lines += len(zero_cost_lines)

print(f"Found {len(grns_with_zero_costs)} GRNs with items having zero cost prices\n")
print("=" * 80)

for item in grns_with_zero_costs:
    grn = item['grn']
    zero_count = len(item['zero_cost_lines'])
    total_count = item['total_lines']
    print(f"\nGRN: {grn.document_number}")
    print(f"  Date: {grn.receipt_date}")
    print(f"  Supplier: {grn.supplier.name if grn.supplier else 'N/A'}")
    print(f"  Items with Zero Cost Price: {zero_count}/{total_count} lines")
    
    # Show the zero-cost lines
    for line in item['zero_cost_lines']:
        po_line = None
        if grn.purchase_order:
            po_line = grn.purchase_order.lines.filter(item=line.item).first()
        
        print(f"    - Item: {line.item.code} ({line.item.name})")
        print(f"      Qty: {line.qty} {line.unit.abbreviation}")
        print(f"      Item Cost Price: ₱{line.item.cost_price}")
        if po_line:
            print(f"      PO Unit Price: ₱{po_line.unit_price}")
        print(f"      Location: {line.location.name if line.location else 'N/A'}")

print("\n" + "=" * 80)
print(f"Total GRNs with zero-cost items: {len(grns_with_zero_costs)}")
print(f"Total lines with zero-cost items: {total_zero_cost_lines}")

