"""
Management command to manually synchronize Sales Orders with their related documents.
Usage: python manage.py sync_sales_orders [--sales-order SO-001] [--all] [--dry-run]
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from decimal import Decimal

from sales.models import SalesOrder
from sales.signals import _sync_invoices, _sync_deliveries, _sync_pickups


class Command(BaseCommand):
    help = 'Manually synchronize Sales Orders with related Invoices, Deliveries, and Pickups'

    def add_arguments(self, parser):
        parser.add_argument(
            '--sales-order',
            type=str,
            help='Specific Sales Order document number to sync (e.g., SO-001)',
        )
        parser.add_argument(
            '--all',
            action='store_true',
            help='Sync all Sales Orders',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be synced without making changes',
        )
        parser.add_argument(
            '--invoices-only',
            action='store_true',
            help='Only sync invoices',
        )
        parser.add_argument(
            '--deliveries-only',
            action='store_true',
            help='Only sync deliveries',
        )
        parser.add_argument(
            '--pickups-only',
            action='store_true',
            help='Only sync pickups',
        )

    def handle(self, *args, **options):
        sales_order_number = options.get('sales_order')
        sync_all = options.get('all')
        dry_run = options.get('dry_run')
        invoices_only = options.get('invoices_only')
        deliveries_only = options.get('deliveries_only')
        pickups_only = options.get('pickups_only')

        if dry_run:
            self.stdout.write(self.style.WARNING('🔍 DRY RUN MODE - No changes will be made'))

        # Determine which Sales Orders to sync
        if sales_order_number:
            sales_orders = SalesOrder.objects.filter(document_number=sales_order_number)
            if not sales_orders.exists():
                self.stdout.write(self.style.ERROR(f'❌ Sales Order {sales_order_number} not found'))
                return
        elif sync_all:
            sales_orders = SalesOrder.objects.all()
        else:
            self.stdout.write(self.style.ERROR('❌ Please specify --sales-order or --all'))
            return

        total_count = sales_orders.count()
        self.stdout.write(f'\n📋 Found {total_count} Sales Order(s) to process\n')

        synced_invoices = 0
        synced_deliveries = 0
        synced_pickups = 0

        for so in sales_orders:
            self.stdout.write(f'\n{"="*60}')
            self.stdout.write(f'Processing: {so.document_number}')
            self.stdout.write(f'{"="*60}')

            # Count related documents
            invoice_count = so.invoices.filter(is_void=False).count()
            delivery_count = so.deliveries.filter(status='DRAFT').count()
            pickup_count = so.pickups.filter(status='DRAFT').count()

            self.stdout.write(f'  📄 Non-void Invoices: {invoice_count}')
            self.stdout.write(f'  🚚 Draft Deliveries: {delivery_count}')
            self.stdout.write(f'  📦 Draft Pickups: {pickup_count}')

            if not dry_run:
                with transaction.atomic():
                    # Sync based on options
                    if not deliveries_only and not pickups_only:
                        if invoice_count > 0:
                            _sync_invoices(so)
                            synced_invoices += invoice_count
                            self.stdout.write(self.style.SUCCESS(f'  ✅ Synced {invoice_count} invoice(s)'))

                    if not invoices_only and not pickups_only:
                        if delivery_count > 0:
                            _sync_deliveries(so)
                            synced_deliveries += delivery_count
                            self.stdout.write(self.style.SUCCESS(f'  ✅ Synced {delivery_count} delivery(ies)'))

                    if not invoices_only and not deliveries_only:
                        if pickup_count > 0:
                            _sync_pickups(so)
                            synced_pickups += pickup_count
                            self.stdout.write(self.style.SUCCESS(f'  ✅ Synced {pickup_count} pickup(s)'))
            else:
                self.stdout.write(self.style.WARNING('  🔍 Would sync (dry run)'))

        # Summary
        self.stdout.write(f'\n{"="*60}')
        self.stdout.write(self.style.SUCCESS('SUMMARY'))
        self.stdout.write(f'{"="*60}')
        self.stdout.write(f'Sales Orders Processed: {total_count}')
        
        if not dry_run:
            self.stdout.write(f'Invoices Synced: {synced_invoices}')
            self.stdout.write(f'Deliveries Synced: {synced_deliveries}')
            self.stdout.write(f'Pickups Synced: {synced_pickups}')
            self.stdout.write(self.style.SUCCESS('\n✅ Synchronization completed successfully!'))
        else:
            self.stdout.write(self.style.WARNING('\n🔍 Dry run completed - no changes made'))
