# Generated migration to add unit_cost field to ServiceOtherMaterial

from django.db import migrations, models
from decimal import Decimal


def backfill_unit_cost(apps, schema_editor):
    """
    Backfill unit_cost with unit_price for existing records.
    This assumes zero margin on historical other materials.
    Adjust manually if you know the actual costs.
    """
    ServiceOtherMaterial = apps.get_model('services', 'ServiceOtherMaterial')
    for mat in ServiceOtherMaterial.objects.all():
        mat.unit_cost = mat.unit_price
        mat.save(update_fields=['unit_cost'])


class Migration(migrations.Migration):

    dependencies = [
        ('services', '0009_serviceline_is_scrap'),
    ]

    operations = [
        migrations.AddField(
            model_name='serviceothermaterial',
            name='unit_cost',
            field=models.DecimalField(
                decimal_places=4,
                default=0,
                help_text='Cost per unit paid to vendor (for COGS calculation)',
                max_digits=15
            ),
        ),
        migrations.RunPython(backfill_unit_cost, reverse_code=migrations.RunPython.noop),
    ]
