"""
Management command to seed default roles for the WIS system.
Usage: python manage.py seed_roles
"""
from django.core.management.base import BaseCommand
from accounts.models import Role


DEFAULT_ROLES = [
    {
        'name': 'Admin',
        'description': 'Full system access. Can manage users, roles, settings, and all modules.',
    },
    {
        'name': 'Manager',
        'description': 'Can approve/post documents, view reports, manage catalog and partners. Cannot manage users or system settings.',
    },
    {
        'name': 'Manager (View Only)',
        'description': 'Can view all modules but cannot create, edit, delete, or post any records. Read-only access across the system.',
    },
    {
        'name': 'Procurement Officer',
        'description': 'Can create/edit purchase orders and goods receipts. Can approve POs. Can view catalog and partners.',
    },
    {
        'name': 'Sales Officer',
        'description': 'Can create/edit sales orders and delivery notes. Can approve SOs. Can view catalog, partners, and inventory.',
    },
    {
        'name': 'Warehouse Staff',
        'description': 'Can create/edit transfers, adjustments, and damaged reports. Can receive goods (GRN). Can view stock balances.',
    },
    {
        'name': 'POS Cashier',
        'description': 'Can operate POS terminal, open/close shifts, process sales and refunds. Limited to POS module.',
    },
    {
        'name': 'Viewer',
        'description': 'Read-only access to catalog items only. Cannot access dashboard, reports, or any other module.',
    },
    {
        'name': 'Web Version',
        'description': 'Read-only access to all modules except Adjustments and POS. Cannot create, edit, delete, or post any records.',
    },
    {
        'name': 'Checker',
        'description': 'Read-only access to all modules except Adjustments and POS. Cannot create, edit, delete, or post any records. (Same as Web Version)',
    },
    {
        'name': 'Encoder',
        'description': 'Can create and edit documents but cannot approve or post. Limited write access.',
    },
    {
        'name': 'Warehouse Manager',
        'description': 'Full access to warehouse operations including transfers, adjustments, and inventory management.',
    },
]


class Command(BaseCommand):
    help = 'Seed default roles for the WIS system'

    def handle(self, *args, **options):
        created_count = 0
        for role_data in DEFAULT_ROLES:
            role, created = Role.objects.get_or_create(
                name=role_data['name'],
                defaults={'description': role_data['description']},
            )
            if created:
                created_count += 1
                self.stdout.write(self.style.SUCCESS(f'  Created role: {role.name}'))
            else:
                self.stdout.write(f'  Role already exists: {role.name}')

        self.stdout.write(self.style.SUCCESS(f'\nDone. {created_count} new roles created.'))
