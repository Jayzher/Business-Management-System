#!/usr/bin/env python
"""Delete the existing conversion from the Neon database."""
import os
import django

# Force use of Neon database (not local SQLite)
os.environ['OFFLINE_MODE'] = '0'  # Ensure we're NOT in offline mode
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'inventory_system.settings')
django.setup()

from catalog.models import Item, UnitConversion
from django.db import connection

print(f"Connected to database: {connection.settings_dict['NAME']}")
print(f"Database engine: {connection.settings_dict['ENGINE']}")
print()

# Get the item
try:
    item = Item.objects.get(pk=1990)
    print(f"Item: {item.code} - {item.name}")
    print()
except Item.DoesNotExist:
    print("Item with ID 1990 not found!")
    exit(1)

# Find the existing conversion
existing = UnitConversion.objects.filter(
    item_id=1990,
    from_unit_id=1,
    to_unit_id=13
)

print(f"Found {existing.count()} existing Piece → Foot conversion(s) for this item")
print()

if existing.exists():
    for conv in existing:
        print(f"Conversion ID: {conv.pk}")
        print(f"  From: {conv.from_unit}")
        print(f"  To: {conv.to_unit}")
        print(f"  Factor: {conv.factor}")
        print(f"  Conversion Price: {conv.conversion_price}")
        print()
    
    response = input("Do you want to DELETE this conversion? (yes/no): ")
    if response.lower() == 'yes':
        count = existing.count()
        existing.delete()
        print(f"\n✓ Deleted {count} conversion(s)")
        print("You can now create a new conversion via the web interface.")
    else:
        print("\nCancelled. No changes made.")
else:
    print("No existing conversion found in the database.")
    print("The conversion might have been deleted already, or you're connected to the wrong database.")
