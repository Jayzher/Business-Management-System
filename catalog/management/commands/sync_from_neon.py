"""
Management command to sync data from Neon (remote) database to local SQLite database.

Usage:
    python manage.py sync_from_neon
    python manage.py sync_from_neon --tables catalog.Item catalog.UnitConversion
    python manage.py sync_from_neon --full  # Sync all tables
"""
import os
from django.core.management.base import BaseCommand
from django.core.management import call_command
from django.db import connections
from django.apps import apps
import tempfile


class Command(BaseCommand):
    help = 'Sync data from Neon (remote) database to local SQLite database'

    def add_arguments(self, parser):
        parser.add_argument(
            '--tables',
            nargs='+',
            help='Specific tables to sync (e.g., catalog.Item catalog.UnitConversion)',
        )
        parser.add_argument(
            '--full',
            action='store_true',
            help='Sync all tables (full database sync)',
        )

    def handle(self, *args, **options):
        # Check if we're in offline mode
        if os.environ.get('OFFLINE_MODE') == '1':
            self.stdout.write(self.style.ERROR(
                'Cannot sync: OFFLINE_MODE is enabled. '
                'Set OFFLINE_MODE=0 in your environment to connect to Neon.'
            ))
            return

        # Verify we have both databases configured
        if 'default' not in connections:
            self.stdout.write(self.style.ERROR('Default database not configured'))
            return

        # Get database info
        neon_db = connections['default']
        neon_engine = neon_db.settings_dict['ENGINE']
        
        self.stdout.write(self.style.SUCCESS(f'Connected to Neon database'))
        self.stdout.write(f'  Engine: {neon_engine}')
        self.stdout.write(f'  Host: {neon_db.settings_dict.get("HOST", "N/A")}')
        self.stdout.write('')

        # Determine which models to sync
        if options['tables']:
            models_to_sync = []
            for table_name in options['tables']:
                try:
                    app_label, model_name = table_name.split('.')
                    model = apps.get_model(app_label, model_name)
                    models_to_sync.append(model)
                except (ValueError, LookupError) as e:
                    self.stdout.write(self.style.ERROR(f'Invalid table: {table_name} - {e}'))
                    return
        elif options['full']:
            # Sync all models
            models_to_sync = apps.get_models()
        else:
            # Default: sync catalog models
            models_to_sync = [
                apps.get_model('catalog', 'Category'),
                apps.get_model('catalog', 'Unit'),
                apps.get_model('catalog', 'UnitConversion'),
                apps.get_model('catalog', 'Item'),
            ]

        self.stdout.write(self.style.SUCCESS(f'Syncing {len(models_to_sync)} model(s)...'))
        self.stdout.write('')

        # Create a temporary file for the dump
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as tmp_file:
            tmp_filename = tmp_file.name

        try:
            # Step 1: Dump data from Neon
            self.stdout.write('Step 1: Exporting data from Neon...')
            model_labels = [f'{m._meta.app_label}.{m._meta.model_name}' for m in models_to_sync]
            
            call_command(
                'dumpdata',
                *model_labels,
                output=tmp_filename,
                format='json',
                indent=2,
                use_natural_foreign_keys=True,
                use_natural_primary_keys=False,
            )
            self.stdout.write(self.style.SUCCESS(f'  ✓ Exported to {tmp_filename}'))
            self.stdout.write('')

            # Step 2: Switch to local SQLite and load data
            self.stdout.write('Step 2: Importing data to local SQLite...')
            
            # Temporarily set OFFLINE_MODE to use SQLite
            original_offline = os.environ.get('OFFLINE_MODE')
            os.environ['OFFLINE_MODE'] = '1'
            
            # Reload Django settings to use SQLite
            from django.conf import settings
            from importlib import reload
            import inventory_system.settings as settings_module
            reload(settings_module)
            
            # Close existing connections
            connections.close_all()
            
            # Load data into SQLite
            call_command(
                'loaddata',
                tmp_filename,
                verbosity=2,
            )
            
            # Restore original OFFLINE_MODE
            if original_offline is not None:
                os.environ['OFFLINE_MODE'] = original_offline
            else:
                del os.environ['OFFLINE_MODE']
            
            self.stdout.write('')
            self.stdout.write(self.style.SUCCESS('✓ Sync completed successfully!'))
            self.stdout.write('')
            self.stdout.write('Synced models:')
            for model in models_to_sync:
                self.stdout.write(f'  - {model._meta.app_label}.{model._meta.model_name}')

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error during sync: {e}'))
            import traceback
            traceback.print_exc()
        finally:
            # Clean up temp file
            if os.path.exists(tmp_filename):
                os.unlink(tmp_filename)
