from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0007_unitconversion_item'),
    ]

    operations = [
        migrations.AddField(
            model_name='unitconversion',
            name='conversion_price',
            field=models.DecimalField(
                blank=True,
                decimal_places=4,
                help_text='Explicit selling price per 1 to_unit when using this conversion. If set, overrides the factor-based price calculation for selling price lookups. COGS always uses cost_price regardless of this field. Example: Roll\u2192ft with factor=5 and conversion_price=30 means each ft sells for 30.',
                max_digits=15,
                null=True,
            ),
        ),
    ]
