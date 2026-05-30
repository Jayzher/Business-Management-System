#!/usr/bin/env python
"""Quick sync of UnitConversion table from Neon to local SQLite."""
import os
import django

print("Connecting to Neon database...")
os.environ['OFFLINE_MODE'] = '0'
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'inventory_system.settings')
django.setup()

from catalog.models import UnitConversion
from django.db import connection

print(f"Connected to: {connection.settings_dict.get('NAME', 'Unknown')}")
print()

# Get all conversions from Neon
print("Fetching conversions from Neon...")
neon_conversions = list(UnitConversion.objects.all().values(
    'id', 'from_unit_id', 'to_unit_id', 'factor', 'conversion_price', 
    'item_id', 'is_active', 'created_at', 'updated_at'
))

print(f"Found {len(neon_conversions)} conversions in Neon")
print()

# Save to a Python file that can be imported
output_file = 'neon_conversions_data.py'
with open(output_file, 'w') as f:
    f.write('# Auto-generated: UnitConversion data from Neon\n')
    f.write('# Run: python load_neon_conversions.py\n\n')
    f.write('conversions = [\n')
    for conv in neon_conversions:
        f.write(f'    {repr(conv)},\n')
    f.write(']\n')

print(f"✓ Saved {len(neon_conversions)} conversions to {output_file}")
print()
print("Now run: python load_neon_conversions.py")
