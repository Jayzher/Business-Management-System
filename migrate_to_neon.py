"""
Migrate all data from local SQLite to Neon PostgreSQL using bulk operations.
Uses Django's multi-database support for fast transfer.
"""
import os, sys, django

# Point default DB at Neon, add sqlite as secondary
os.environ['DJANGO_SETTINGS_MODULE'] = 'inventory_system.settings'
os.environ.pop('DATABASE_URL', None)  # ensure we use our manual config

import django
from django.conf import settings

# Override DATABASES before django.setup()
NEON_URL = 'postgresql://neondb_owner:npg_KhjsX3uB0mil@ep-raspy-hall-a1fl4lfx.ap-southeast-1.aws.neon.tech/neondb?sslmode=require'

import dj_database_url

settings.DATABASES = {
    'default': dj_database_url.parse(NEON_URL, conn_max_age=600, ssl_require=True),
    'sqlite': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': os.path.join(os.path.dirname(__file__), 'db.sqlite3'),
    },
}

django.setup()

from django.apps import apps
from django.db import connections
from django.core.management import call_command

BATCH_SIZE = 500

# Step 1: Flush Neon DB
print("=" * 60)
print("Step 1: Flushing Neon DB...")
print("=" * 60)
call_command('flush', '--no-input', database='default')
print("Flushed.\n")

# Step 2: Copy data model by model
print("=" * 60)
print("Step 2: Copying data from SQLite -> Neon PostgreSQL")
print("=" * 60)

# Get all models in dependency order
all_models = apps.get_models(include_auto_created=True)

total_copied = 0
errors = []

for model in all_models:
    model_name = f"{model._meta.app_label}.{model._meta.model_name}"
    try:
        # Read all objects from SQLite
        objs = list(model.objects.using('sqlite').all())
        count = len(objs)
        if count == 0:
            print(f"  SKIP  {model_name} (empty)")
            continue

        # Disable auto-fields so PKs are preserved
        for obj in objs:
            obj._state.adding = True
            obj._state.db = 'default'

        # Bulk create in batches, ignoring conflicts for safety
        for i in range(0, count, BATCH_SIZE):
            batch = objs[i:i + BATCH_SIZE]
            model.objects.using('default').bulk_create(batch, batch_size=BATCH_SIZE, ignore_conflicts=True)

        total_copied += count
        print(f"  OK    {model_name}: {count} rows")
    except Exception as e:
        err_msg = f"  ERROR {model_name}: {e}"
        print(err_msg)
        errors.append(err_msg)

# Step 3: Reset sequences for PostgreSQL
print("\n" + "=" * 60)
print("Step 3: Resetting PostgreSQL sequences...")
print("=" * 60)

with connections['default'].cursor() as cursor:
    for model in all_models:
        if not model._meta.managed:
            continue
        db_table = model._meta.db_table
        pk_col = model._meta.pk.column if model._meta.pk else None
        if pk_col:
            try:
                cursor.execute(f"""
                    SELECT setval(
                        pg_get_serial_sequence('{db_table}', '{pk_col}'),
                        COALESCE((SELECT MAX("{pk_col}") FROM "{db_table}"), 1),
                        true
                    )
                """)
            except Exception:
                pass  # table might not have a serial sequence

print("Sequences reset.\n")

# Summary
print("=" * 60)
print(f"Migration complete! {total_copied} total rows copied.")
if errors:
    print(f"\n{len(errors)} errors:")
    for e in errors:
        print(e)
else:
    print("No errors!")
print("=" * 60)
