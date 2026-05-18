#!/usr/bin/env python
"""Find the existing conversion in the database."""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'inventory_system.settings')
django.setup()

from catalog.models import Item, UnitConversion

# Get the item
item = Item.objects.get(pk=1990)
print(f"Item: {item.code} - {item.name}")
print(f"Item ID: {item.pk}")
print()

# Find the existing conversion
existing = UnitConversion.objects.filter(
    item_id=1990,
    from_unit_id=1,
    to_unit_id=13
)

print(f"Existing Piece → Foot conversions for this item: {existing.count()}")
print()

for conv in existing:
    print(f"Conversion ID: {conv.pk}")
    print(f"  From: {conv.from_unit}")
    print(f"  To: {conv.to_unit}")
    print(f"  Factor: {conv.factor}")
    print(f"  Conversion Price: {conv.conversion_price}")
    print(f"  Active: {conv.is_active}")
    print(f"  Created: {conv.created_at if hasattr(conv, 'created_at') else 'N/A'}")
    print()

if existing.exists():
    print("="*70)
    print("SOLUTION:")
    print("="*70)
    print("This conversion already exists! You have two options:")
    print()
    print("1. EDIT the existing conversion:")
    print(f"   - Go to the item edit page")
    print(f"   - The conversion should already be shown in the formset")
    print(f"   - Modify the Factor or Price values")
    print(f"   - Click Save")
    print()
    print("2. DELETE the existing conversion first, then create a new one:")
    print(f"   - Delete conversion ID: {existing.first().pk}")
    print()
else:
    print("No existing conversion found. This is strange - the database says it exists!")
    print("Try refreshing the page or checking if you're connected to the right database.")
