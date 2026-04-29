"""
Management command: create_capital_transaction
==============================================
Create capital injection transactions (owner investments, loans, etc.)

Usage:
    python manage.py create_capital_transaction --amount 600000 --date 2026-01-15 --reason "Owner capital injection"
    python manage.py create_capital_transaction --amount 100000 --date 2026-02-01 --reason "Additional investment" --user admin
"""
from decimal import Decimal
from datetime import datetime
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.utils import timezone
from cashflow.models import (
    CashFlowTransaction, CashFlowCategory, 
    CashFlowType, CashFlowStatus, PaymentMethod
)

User = get_user_model()


class Command(BaseCommand):
    help = 'Create a capital injection transaction'

    def add_arguments(self, parser):
        parser.add_argument('--amount', type=float, required=True, help='Amount of capital injection')
        parser.add_argument('--date', type=str, required=True, help='Transaction date (YYYY-MM-DD)')
        parser.add_argument('--reason', type=str, required=True, help='Reason for capital injection')
        parser.add_argument('--user', type=str, default='admin', help='Username of creator (default: admin)')
        parser.add_argument('--payment-method', type=str, default='BANK_TRANSFER', 
                          choices=['CASH', 'CHECK', 'BANK_TRANSFER', 'GCASH', 'CARD', 'OTHER'],
                          help='Payment method')
        parser.add_argument('--reference', type=str, default='', help='Reference number')
        parser.add_argument('--dry-run', action='store_true', help='Preview without saving')

    def handle(self, *args, **options):
        amount = Decimal(str(options['amount']))
        date_str = options['date']
        reason = options['reason']
        username = options['user']
        payment_method = options['payment_method']
        reference = options['reference']
        dry_run = options['dry_run']

        # Parse date
        try:
            transaction_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            self.stdout.write(self.style.ERROR(f'Invalid date format: {date_str}. Use YYYY-MM-DD'))
            return

        # Get user
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'User not found: {username}'))
            self.stdout.write('Available users:')
            for u in User.objects.all()[:10]:
                self.stdout.write(f'  - {u.username}')
            return

        # Generate transaction number
        transaction_number = CashFlowTransaction.generate_next_number()

        # Display preview
        self.stdout.write(self.style.SUCCESS('\n=== Capital Transaction Preview ===\n'))
        self.stdout.write(f'Transaction Number: {transaction_number}')
        self.stdout.write(f'Category:           CAPITAL')
        self.stdout.write(f'Flow Type:          CASH IN')
        self.stdout.write(f'Amount:             ₱{amount:,.2f}')
        self.stdout.write(f'Date:               {transaction_date}')
        self.stdout.write(f'Payment Method:     {payment_method}')
        self.stdout.write(f'Reference:          {reference or "(none)"}')
        self.stdout.write(f'Reason:             {reason}')
        self.stdout.write(f'Created By:         {user.username}')
        self.stdout.write(f'Status:             APPROVED')

        if dry_run:
            self.stdout.write(self.style.WARNING('\nDry-run mode - No changes made'))
            return

        # Create transaction
        try:
            txn = CashFlowTransaction.objects.create(
                transaction_number=transaction_number,
                category=CashFlowCategory.CAPITAL,
                flow_type=CashFlowType.CASH_IN,
                amount=amount,
                transaction_date=transaction_date,
                payment_method=payment_method,
                reference_no=reference,
                reason=reason,
                status=CashFlowStatus.APPROVED,
                created_by=user,
                approved_by=user,
                approved_at=timezone.now()
            )

            self.stdout.write(self.style.SUCCESS(f'\n✓ Capital transaction created: {txn.transaction_number}'))
            self.stdout.write(self.style.SUCCESS(f'  Amount: ₱{txn.amount:,.2f}'))
            self.stdout.write(self.style.SUCCESS(f'  Date: {txn.transaction_date}'))
            
            self.stdout.write(self.style.WARNING('\nNext steps:'))
            self.stdout.write('  1. Verify transaction in admin or database')
            self.stdout.write(f'  2. Recalculate financial statements:')
            self.stdout.write(f'     python manage.py calculate_financial_statements --year {transaction_date.year} --month {transaction_date.month}')

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'\n✗ Error creating transaction: {str(e)}'))
