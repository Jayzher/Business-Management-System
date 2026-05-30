"""Load data into Neon DB."""
import os, sys, django

os.environ['DATABASE_URL'] = 'postgresql://neondb_owner:npg_KhjsX3uB0mil@ep-raspy-hall-a1fl4lfx.ap-southeast-1.aws.neon.tech/neondb?sslmode=require'
os.environ['DJANGO_SETTINGS_MODULE'] = 'inventory_system.settings'

django.setup()

from django.core.management import call_command

print("Loading data into Neon DB...")
call_command('loaddata', 'full_dump.json')
print("Done!")
