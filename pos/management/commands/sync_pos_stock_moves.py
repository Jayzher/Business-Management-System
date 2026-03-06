from django.core.management.base import BaseCommand
from django.db import transaction

from pos.models import POSSale, SaleStatus
from pos.services.checkout import sync_pos_sale_stock_moves


class Command(BaseCommand):
    help = 'Backfill/sync missing inventory StockMove rows for completed POS receipts.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--limit',
            type=int,
            default=200,
            help='Max number of receipts to process in this run (default: 200).'
        )

    def handle(self, *args, **options):
        limit = options['limit']

        qs = POSSale.objects.filter(
            status__in=[SaleStatus.PAID, SaleStatus.POSTED],
            stock_deducted=False,
        ).order_by('id')

        if limit:
            qs = qs[:limit]

        processed = 0
        fixed = 0

        for sale in qs:
            processed += 1
            try:
                with transaction.atomic():
                    before = sale.stock_deducted
                    sync_pos_sale_stock_moves(sale.pk, sale.created_by)
                    sale.refresh_from_db()
                    if not before and sale.stock_deducted:
                        fixed += 1
                        self.stdout.write(self.style.SUCCESS(f'Fixed {sale.sale_no} (id={sale.pk})'))
                    else:
                        self.stdout.write(f'Skipped {sale.sale_no} (id={sale.pk})')
            except Exception as e:
                self.stderr.write(self.style.ERROR(f'Error on {sale.sale_no} (id={sale.pk}): {e}'))

        self.stdout.write(self.style.SUCCESS(f'Done. Processed={processed}, Fixed={fixed}'))
