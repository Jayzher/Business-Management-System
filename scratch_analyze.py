import os
import sys
import django

# Set up Django environment
sys.path.append('D:/PsyChoNyMouz/Projects/BusinessWebsite/Business-Management-System')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'inventory_system.settings')
django.setup()

from catalog.models import Item, UnitConversion, Unit
from inventory.models import StockMove
from django.db.models import Q

items_to_check = [
    "ACC-ALCOMESH #36-HA",
    "ACC-ALCOMESH #36-PCW",
    "ACC-ExpandWire#36-HA",
    "ACC-RedMo-S",
    "ACC-ScreenMesh-#36-HA",
    "ACC-ScreenMesh-#48-A",
    "TOO-Tox-5"
]

print("=== CHECKING ITEMS ===")
items = Item.objects.filter(code__in=items_to_check)
for item in items:
    print(f"Item Code: {item.code}")
    print(f"  Name: {item.name}")
    print(f"  Default/Procurement Unit: {item.default_unit} (ID: {item.default_unit_id})")
    print(f"  Selling Unit: {item.selling_unit} (ID: {item.selling_unit_id})")
    
    # Check conversions for this specific item or globally
    convs = UnitConversion.objects.filter(
        Q(item=item) | Q(item__isnull=True)
    ).filter(
        Q(from_unit=item.default_unit) | Q(to_unit=item.default_unit) |
        Q(from_unit=item.selling_unit) | Q(to_unit=item.selling_unit)
    )
    print("  Conversions:")
    for conv in convs:
        print(f"    - {conv.from_unit} -> {conv.to_unit} (factor: {conv.factor}, item: {conv.item.code if conv.item else 'Global'})")

print("\n=== SEARCHING DOCUMENT REFERENCES ===")
from procurement.models import GoodsReceiptLine, PurchaseReturnLine
from sales.models import DeliveryLine, SalesPickupLine, SalesReturnLine
from inventory.models import StockTransferLine, StockAdjustmentLine, DamagedReportLine, InventoryToSupplyTransferLine
from pos.models import POSSaleLine, POSRefundLine
from services.models import ServiceLine

models_to_check = [
    ('GoodsReceiptLine', GoodsReceiptLine, 'goods_receipt'),
    ('DeliveryLine', DeliveryLine, 'delivery'),
    ('SalesPickupLine', SalesPickupLine, 'pickup'),
    ('StockTransferLine', StockTransferLine, 'transfer'),
    ('StockAdjustmentLine', StockAdjustmentLine, 'adjustment'),
    ('DamagedReportLine', DamagedReportLine, 'report'),
    ('POSSaleLine', POSSaleLine, 'sale'),
    ('POSRefundLine', POSRefundLine, 'refund'),
    ('InventoryToSupplyTransferLine', InventoryToSupplyTransferLine, 'transfer'),
    ('PurchaseReturnLine', PurchaseReturnLine, 'purchase_return'),
    ('SalesReturnLine', SalesReturnLine, 'sales_return'),
    ('ServiceLine', ServiceLine, 'service'),
]

for name, model, fk_field in models_to_check:
    lines = model.objects.filter(item__code__in=items_to_check)
    if lines.exists():
        print(f"\nReferences in {name}:")
        for line in lines:
            doc = getattr(line, fk_field)
            doc_status = getattr(doc, 'status', 'N/A')
            doc_num = getattr(doc, 'document_number', None) or getattr(doc, 'sale_no', None) or getattr(doc, 'refund_no', None) or getattr(doc, 'service_number', None) or getattr(doc, 'pk', '?')
            print(f"  Doc: {doc_num} (Status: {doc_status}) | Item: {line.item.code} | Qty: {line.qty if hasattr(line, 'qty') else (getattr(line, 'qty_counted', 0) - getattr(line, 'qty_system', 0))} | Unit: {line.unit} (ID: {line.unit_id})")

print("\n=== SEARCHING STOCK MOVES ===")
moves = StockMove.objects.filter(item__code__in=items_to_check, status='POSTED')
if moves.exists():
    print(f"Posted StockMoves:")
    for move in moves:
        print(f"  Move ID: {move.pk} | Ref: {move.reference_type} #{move.reference_id} ({move.reference_number}) | Item: {move.item.code} | Qty: {move.qty} | Unit: {move.unit} (ID: {move.unit_id})")
