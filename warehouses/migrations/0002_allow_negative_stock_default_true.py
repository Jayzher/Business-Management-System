"""
Change allow_negative_stock default to True and update all existing warehouses.
"""
from django.db import migrations, models


def enable_negative_stock(apps, schema_editor):
    """Set allow_negative_stock=True on all existing warehouses."""
    Warehouse = apps.get_model('warehouses', 'Warehouse')
    Warehouse.objects.all().update(allow_negative_stock=True)


def disable_negative_stock(apps, schema_editor):
    """Reverse: set allow_negative_stock=False on all existing warehouses."""
    Warehouse = apps.get_model('warehouses', 'Warehouse')
    Warehouse.objects.all().update(allow_negative_stock=False)


class Migration(migrations.Migration):

    dependencies = [
        ('warehouses', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='warehouse',
            name='allow_negative_stock',
            field=models.BooleanField(default=True),
        ),
        migrations.RunPython(enable_negative_stock, disable_negative_stock),
    ]
