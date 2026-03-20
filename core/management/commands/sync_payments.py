"""
Management command: sync_payments

Backfills InvoicePayment records and paid_date for invoices that have
is_paid=True but are missing payment history or a paid_date value.

Usage:
  python manage.py sync_payments              # live run (default)
  python manage.py sync_payments --dry-run    # preview without saving
  python manage.py sync_payments --cogs       # also resync grand_total_cogs
"""
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.utils import timezone
from core.cogs import compute_invoice_cogs


class Command(BaseCommand):
    help = 'Sync InvoicePayment records and paid_date for all paid invoices.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Preview changes without writing to the database.',
        )
        parser.add_argument(
            '--cogs', action='store_true',
            help='Also recompute grand_total_cogs for every synced invoice.',
        )

    def handle(self, *args, **options):
        from core.models import Invoice, InvoicePayment, PaymentMethod

        dry_run = options['dry_run']
        do_cogs = options['cogs']

        paid_date_fixed = 0
        payments_created = 0
        cogs_updated = 0

        qs = Invoice.objects.prefetch_related('payments').select_related(
            'pos_sale', 'sales_order',
        )

        for inv in qs.iterator(chunk_size=500):
            changed = False

            # ── 1. Backfill paid_date ─────────────────────────────────────
            if inv.is_paid and not inv.paid_date:
                # Try latest payment date, then paid_at, then invoice date
                latest_payment = inv.payments.order_by('-date').first()
                if latest_payment:
                    new_paid_date = latest_payment.date
                elif inv.paid_at:
                    new_paid_date = inv.paid_at.date()
                else:
                    new_paid_date = inv.date

                if not dry_run:
                    inv.paid_date = new_paid_date
                    inv.save(update_fields=['paid_date'])
                self.stdout.write(
                    f'  [PAID_DATE] INV-{inv.invoice_number} → {new_paid_date}'
                )
                paid_date_fixed += 1
                changed = True

            # ── 2. Create missing InvoicePayment record ───────────────────
            if inv.is_paid and not inv.payments.exists():
                paid_date = inv.paid_date or inv.date
                ref = ''
                notes = 'Auto-synced payment record'
                if inv.pos_sale_id:
                    ref = getattr(inv.pos_sale, 'sale_no', '')
                    notes = 'Auto-synced from POS sale'
                elif inv.sales_order_id:
                    ref = getattr(inv.sales_order, 'document_number', '')
                    notes = 'Auto-synced from Sales Order'

                if not dry_run:
                    # Use the admin user if available, otherwise first superuser
                    from django.contrib.auth import get_user_model
                    User = get_user_model()
                    creator = inv.created_by
                    InvoicePayment.objects.create(
                        invoice=inv,
                        date=paid_date,
                        method=PaymentMethod.CASH,
                        amount=inv.grand_total,
                        reference_no=ref,
                        notes=notes,
                        created_by=creator,
                    )
                self.stdout.write(
                    f'  [PAYMENT]   INV-{inv.invoice_number} '
                    f'₱{inv.grand_total:,.2f} on {paid_date}'
                )
                payments_created += 1
                changed = True

            # ── 3. Optionally resync COGS ─────────────────────────────────
            if do_cogs and inv.is_paid:
                cogs = self._compute_cogs(inv)
                if inv.grand_total_cogs != cogs:
                    if not dry_run:
                        inv.grand_total_cogs = cogs
                        inv.save(update_fields=['grand_total_cogs'])
                    self.stdout.write(
                        f'  [COGS]      INV-{inv.invoice_number} '
                        f'old={inv.grand_total_cogs:,.2f} → new={cogs:,.2f}'
                    )
                    cogs_updated += 1

        prefix = '[DRY-RUN] ' if dry_run else ''
        self.stdout.write(self.style.SUCCESS(
            f'\n{prefix}Sync complete:\n'
            f'  paid_date backfilled : {paid_date_fixed}\n'
            f'  payments created     : {payments_created}\n'
            f'  COGS updated         : {cogs_updated}'
        ))

    def _compute_cogs(self, inv):
        return compute_invoice_cogs(inv)
