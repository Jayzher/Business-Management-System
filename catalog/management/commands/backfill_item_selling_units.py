from django.core.management.base import BaseCommand
from django.db import transaction


class Command(BaseCommand):
    help = 'Set Item.selling_unit = default_unit for items where selling_unit is blank.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Preview the items that would be updated without saving changes.',
        )

    def handle(self, *args, **options):
        from catalog.models import Item

        dry_run = options['dry_run']
        qs = Item.objects.filter(selling_unit__isnull=True).select_related('default_unit').order_by('code')
        total = qs.count()

        if total == 0:
            self.stdout.write(self.style.SUCCESS('No items found with blank selling_unit.'))
            return

        self.stdout.write(
            f"Found {total} item(s) with blank selling_unit."
            + (' [DRY-RUN]' if dry_run else '')
        )

        updated = 0
        with transaction.atomic():
            for item in qs.iterator(chunk_size=500):
                self.stdout.write(
                    f" - {item.code}: selling_unit=None -> {item.default_unit.abbreviation}"
                )
                if not dry_run:
                    item.selling_unit = item.default_unit
                    item.save(update_fields=['selling_unit', 'updated_at'])
                updated += 1

            if dry_run:
                transaction.set_rollback(True)

        prefix = '[DRY-RUN] ' if dry_run else ''
        self.stdout.write(self.style.SUCCESS(
            f'{prefix}Completed. {updated} item(s) processed.'
        ))
