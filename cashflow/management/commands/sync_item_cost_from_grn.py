"""
Management command: sync_item_cost_from_grn
============================================
Synchronizes Item.cost_price from GRN (Goods Receipt Note) data.

This fixes the "Zero-Value Inventory Asset" bug where inventory purchases
are recorded but the Item.cost_price is never updated, resulting in ₱0
inventory asset values.

The command calculates weighted average cost (WAC) from all GRN lines
for each item and updates the Item.cost_price accordingly.

Usage:
    python manage.py sync_item_cost_from_grn                    # all items
    python manage.py sync_item_cost_from_grn --item-code ABC123 # specific item
    python manage.py sync_item_cost_from_grn --dry-run          # preview only
    python manage.py sync_item_cost_from_grn --recalc-cashflow  # also recalc monthly summaries
"""
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Sum, F, DecimalField
from django.db.models.functions import Coalesce

from catalog.models import Item
from procurement.models import GoodsReceiptLine, GoodsReceipt
from core.models import DocumentStatus


class Command(BaseCommand):
    help = 'Synchronize Item.cost_price from GRN data using weighted average cost'

    def add_arguments(self, parser):
        parser.add_argument(
            '--item-code',
            type=str,
            help='Sync only a specific item by code',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Preview changes without saving',
        )
        parser.add_argument(
            '--recalc-cashflow',
            action='store_true',
            help='After syncing, recalculate monthly cashflow summaries',
        )
        parser.add_argument(
            '--quiet', '-q',
            action='store_true',
            help='Suppress detailed output',
        )

    def handle(self, *args, **options):
        item_code = options.get('item_code')
        dry_run = options['dry_run']
        recalc_cashflow = options['recalc_cashflow']
        self.quiet = options['quiet']

        mode = 'DRY-RUN' if dry_run else 'APPLYING'
        self._info(f'\n=== Sync Item Cost from GRN [{mode}] ===\n')

        # Get items to process
        if item_code:
            items = Item.objects.filter(code=item_code)
            if not items.exists():
                self.stdout.write(self.style.ERROR(f'Item with code "{item_code}" not found'))
                return
        else:
            # Get all items that have stock movements (i.e., have been received)
            items = Item.objects.filter(
                balances__isnull=False
            ).distinct()

        if not items.exists():
            self.stdout.write(self.style.WARNING('No items found to sync'))
            return

        self._info(f'Processing {items.count()} item(s)...\n')

        updated_count = 0
        unchanged_count = 0
        error_count = 0
        total_inventory_value = Decimal('0')

        with transaction.atomic():
            for item in items.order_by('code'):
                try:
                    old_cost = item.cost_price or Decimal('0')
                    new_cost = self._calculate_weighted_average_cost(item)
                    
                    if new_cost is None or new_cost == Decimal('0'):
                        self._info(f'  {item.code:<20} | No GRN data found, cost unchanged at ₱{old_cost:.2f}')
                        unchanged_count += 1
                        continue
                    
                    # Update item cost
                    item.cost_price = new_cost
                    item.save(update_fields=['cost_price'])
                    
                    # Calculate inventory value for this item
                    qty_on_hand = item.balances.aggregate(Sum('qty_on_hand'))['qty_on_hand__sum'] or Decimal('0')
                    item_inventory_value = qty_on_hand * new_cost
                    total_inventory_value += item_inventory_value
                    
                    # Display result
                    change_indicator = '↑' if new_cost > old_cost else '↓' if new_cost < old_cost else '='
                    self._info(
                        f'  {item.code:<20} | {change_indicator} ₱{old_cost:>8.2f} → ₱{new_cost:>8.2f} | '
                        f'Qty: {qty_on_hand:>8.2f} | Value: ₱{item_inventory_value:>12.2f}'
                    )
                    updated_count += 1
                    
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f'  {item.code:<20} | ERROR: {str(e)}'))
                    error_count += 1
                    continue

            if dry_run:
                transaction.set_rollback(True)
                self.stdout.write(self.style.WARNING('\nDry-run complete. No changes saved.'))
            else:
                self.stdout.write(self.style.SUCCESS('\n=== Sync Complete ==='))

        # Summary
        self._info(f'\nSummary:')
        self._info(f'  Updated: {updated_count}')
        self._info(f'  Unchanged: {unchanged_count}')
        self._info(f'  Errors: {error_count}')
        self._info(f'  Total Inventory Value: ₱{total_inventory_value:,.2f}\n')

        # Optionally recalculate cashflow
        if recalc_cashflow and not dry_run:
            self._info('Recalculating monthly cashflow summaries...\n')
            self._recalculate_cashflow()

    def _calculate_weighted_average_cost(self, item):
        """
        Calculate weighted average cost (WAC) for an item from all GRN lines.
        
        Formula: WAC = Sum(Qty × Unit Price) / Sum(Qty)
        
        Returns:
            Decimal: Weighted average cost, or None if no GRN data
        """
        # Get all GRN lines for this item (only from posted GRNs)
        grn_lines = GoodsReceiptLine.objects.filter(
            item=item,
            goods_receipt__status=DocumentStatus.POSTED,
        ).select_related('goods_receipt')

        if not grn_lines.exists():
            return None

        # Calculate total quantity and total cost
        total_qty = Decimal('0')
        total_cost = Decimal('0')

        for line in grn_lines:
            # Get unit price from the linked PurchaseOrder
            po_line = line.goods_receipt.purchase_order.lines.filter(
                item=item
            ).first() if line.goods_receipt.purchase_order else None

            if po_line:
                unit_price = po_line.unit_price
            else:
                # Fallback: try to get from any recent GRN for this item
                unit_price = Decimal('0')

            total_qty += line.qty
            total_cost += line.qty * unit_price

        # Calculate WAC
        if total_qty > 0:
            wac = total_cost / total_qty
            return wac.quantize(Decimal('0.01'))
        
        return None

    def _recalculate_cashflow(self):
        """Recalculate monthly cashflow summaries after cost sync."""
        from django.core.management import call_command
        try:
            call_command('calculate_monthly_cashflow', quiet=self.quiet)
            self.stdout.write(self.style.SUCCESS('Cashflow recalculation complete.\n'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Cashflow recalculation failed: {str(e)}\n'))

    def _info(self, msg):
        """Print info message unless quiet mode is enabled."""
        if not self.quiet:
            self.stdout.write(msg)
