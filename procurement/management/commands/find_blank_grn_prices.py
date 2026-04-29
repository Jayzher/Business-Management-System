from django.core.management.base import BaseCommand
from procurement.models import GoodsReceipt, PurchaseOrderLine
from catalog.models import Item
from django.db.models import Q


class Command(BaseCommand):
    help = 'Find all GRNs with items that have zero or missing cost prices'

    def handle(self, *args, **options):
        """
        GRN lines don't store prices directly. Instead, prices come from:
        1. Related PurchaseOrderLine (if GRN is linked to a PO)
        2. Item.cost_price (weighted average cost)
        3. SupplierCatalogEntry (supplier's price for that item)
        
        This command finds GRNs where items have zero cost_price.
        """
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

        self.stdout.write(f"Found {len(grns_with_zero_costs)} GRNs with items having zero cost prices\n")
        self.stdout.write("=" * 80)

        for item in grns_with_zero_costs:
            grn = item['grn']
            zero_count = len(item['zero_cost_lines'])
            total_count = item['total_lines']
            self.stdout.write(f"\nGRN: {grn.document_number}")
            self.stdout.write(f"  Date: {grn.receipt_date}")
            self.stdout.write(f"  Supplier: {grn.supplier.name if grn.supplier else 'N/A'}")
            self.stdout.write(f"  Items with Zero Cost Price: {zero_count}/{total_count} lines")
            
            # Show the zero-cost lines
            for line in item['zero_cost_lines']:
                po_line = None
                if grn.purchase_order:
                    po_line = grn.purchase_order.lines.filter(item=line.item).first()
                
                self.stdout.write(f"    - Item: {line.item.code} ({line.item.name})")
                self.stdout.write(f"      Qty: {line.qty} {line.unit.abbreviation}")
                self.stdout.write(f"      Item Cost Price: ₱{line.item.cost_price}")
                if po_line:
                    self.stdout.write(f"      PO Unit Price: ₱{po_line.unit_price}")
                self.stdout.write(f"      Location: {line.location.name if line.location else 'N/A'}")

        self.stdout.write("\n" + "=" * 80)
        self.stdout.write(f"Total GRNs with zero-cost items: {len(grns_with_zero_costs)}")
        self.stdout.write(f"Total lines with zero-cost items: {total_zero_cost_lines}")
