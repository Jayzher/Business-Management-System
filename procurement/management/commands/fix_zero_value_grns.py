"""
Management command: fix_zero_value_grns
========================================
Identifies and reports GRNs with zero or missing values.
Provides options to update them with item cost prices.

Usage:
    python manage.py fix_zero_value_grns --report
    python manage.py fix_zero_value_grns --fix
    python manage.py fix_zero_value_grns --fix --year 2026 --month 4
"""
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.db import transaction
from procurement.models import GoodsReceipt
from core.models import DocumentStatus


class Command(BaseCommand):
    help = 'Identify and fix zero-value GRNs'

    def add_arguments(self, parser):
        parser.add_argument('--report', action='store_true', help='Report zero-value GRNs')
        parser.add_argument('--fix', action='store_true', help='Fix zero-value GRNs by updating PO prices')
        parser.add_argument('--year', type=int, help='Filter by year')
        parser.add_argument('--month', type=int, help='Filter by month')

    def handle(self, *args, **options):
        report_only = options['report']
        fix = options['fix']
        year = options.get('year')
        month = options.get('month')

        if not report_only and not fix:
            self.stdout.write(self.style.ERROR('Please specify --report or --fix'))
            return

        self.stdout.write(self.style.SUCCESS('\n=== Zero-Value GRN Checker ===\n'))

        # Build query
        grns = GoodsReceipt.objects.filter(status=DocumentStatus.POSTED)
        
        if year:
            grns = grns.filter(receipt_date__year=year)
        if month:
            grns = grns.filter(receipt_date__month=month)

        grns = grns.prefetch_related('lines__item', 'purchase_order__lines').order_by('receipt_date')

        zero_value_grns = []
        
        for grn in grns:
            grn_total = Decimal('0')
            zero_lines = []
            
            for line in grn.lines.all():
                line_cost = Decimal('0')
                
                # Check PO price
                if grn.purchase_order:
                    po_line = grn.purchase_order.lines.filter(item=line.item).first()
                    if po_line:
                        line_cost = line.qty * po_line.unit_price
                
                if line_cost == 0 and line.qty > 0:
                    zero_lines.append({
                        'line': line,
                        'item_cost': line.item.cost_price or Decimal('0')
                    })
                
                grn_total += line_cost
            
            if zero_lines:
                zero_value_grns.append({
                    'grn': grn,
                    'total': grn_total,
                    'zero_lines': zero_lines
                })

        if not zero_value_grns:
            self.stdout.write(self.style.SUCCESS('✓ No zero-value GRNs found!'))
            return

        self.stdout.write(self.style.WARNING(f'Found {len(zero_value_grns)} GRN(s) with zero-value lines:\n'))

        for entry in zero_value_grns:
            grn = entry['grn']
            self.stdout.write(f'\n{grn.document_number} - {grn.receipt_date} - {grn.supplier.name}')
            self.stdout.write(f'  Current Total: ₱{entry["total"]:,.2f}')
            
            for zl in entry['zero_lines']:
                line = zl['line']
                item_cost = zl['item_cost']
                self.stdout.write(f'  ⚠️  {line.item.code} x {line.qty} - PO Price: ₱0.00, Item Cost: ₱{item_cost:,.2f}')

        if fix:
            self.stdout.write(self.style.WARNING(f'\n\nAttempting to fix {len(zero_value_grns)} GRN(s)...\n'))
            
            with transaction.atomic():
                fixed_count = 0
                skipped_count = 0
                
                for entry in zero_value_grns:
                    grn = entry['grn']
                    
                    if not grn.purchase_order:
                        self.stdout.write(f'  ⚠️  Skipping {grn.document_number} - No PO linked')
                        skipped_count += 1
                        continue
                    
                    fixed_lines = 0
                    for zl in entry['zero_lines']:
                        line = zl['line']
                        item_cost = zl['item_cost']
                        
                        if item_cost > 0:
                            # Update PO line with item cost
                            po_line = grn.purchase_order.lines.filter(item=line.item).first()
                            if po_line:
                                po_line.unit_price = item_cost
                                po_line.save()
                                fixed_lines += 1
                                self.stdout.write(f'  ✓ Fixed {grn.document_number} - {line.item.code}: ₱{item_cost:,.2f}')
                        else:
                            self.stdout.write(f'  ⚠️  Cannot fix {grn.document_number} - {line.item.code}: No cost price available')
                    
                    if fixed_lines > 0:
                        fixed_count += 1
                
                self.stdout.write(self.style.SUCCESS(f'\n✓ Fixed {fixed_count} GRN(s)'))
                if skipped_count > 0:
                    self.stdout.write(self.style.WARNING(f'⚠️  Skipped {skipped_count} GRN(s)'))
                
                self.stdout.write(self.style.SUCCESS('\n=== Fix Complete ==='))
                self.stdout.write(self.style.WARNING('\nPlease run: python manage.py calculate_financial_statements --year 2026'))
        else:
            self.stdout.write(self.style.WARNING('\n\nRun with --fix to update PO prices with item cost prices'))
