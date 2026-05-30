#!/usr/bin/env python
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'inventory_system.settings')
django.setup()

from catalog.models import Unit, UnitConversion, Item
from django.db import models

print("=" * 80)
print("UNITS IN DATABASE")
print("=" * 80)
for u in Unit.objects.all()[:30]:
    print(f"  {u.id}: {u.name} ({u.abbreviation}) - Category: {u.category}")

print("\n" + "=" * 80)
print("UNIT CONVERSIONS IN DATABASE")
print("=" * 80)
for c in UnitConversion.objects.select_related('from_unit', 'to_unit', 'item').all()[:30]:
    item_info = f" [Item: {c.item.code}]" if c.item else " [Global]"
    price_info = f", conversion_price={c.conversion_price}" if c.conversion_price else ""
    print(f"  {c.from_unit.abbreviation} → {c.to_unit.abbreviation}: factor={c.factor}{price_info}{item_info}")

print("\n" + "=" * 80)
print("ITEMS WITH DIFFERENT DEFAULT AND SELLING UNITS")
print("=" * 80)
items = Item.objects.select_related('default_unit', 'selling_unit').exclude(selling_unit__isnull=True).exclude(selling_unit=models.F('default_unit'))[:10]
for item in items:
    print(f"  {item.code}: {item.name}")
    print(f"    Default unit: {item.default_unit.abbreviation}")
    print(f"    Selling unit: {item.selling_unit.abbreviation if item.selling_unit else 'None'}")
    print(f"    Cost price: {item.cost_price}")
    print(f"    Selling price: {item.selling_price}")
    print()
