from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0006_unit_category'),
    ]

    operations = [
        # Drop old unique_together constraint
        migrations.AlterUniqueTogether(
            name='unitconversion',
            unique_together=set(),
        ),
        # Add item FK
        migrations.AddField(
            model_name='unitconversion',
            name='item',
            field=models.ForeignKey(
                blank=True,
                help_text='Leave blank for a global conversion. Set to override the factor for a specific product.',
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='unit_conversions',
                to='catalog.item',
            ),
        ),
        # Add the two partial unique constraints
        migrations.AddConstraint(
            model_name='unitconversion',
            constraint=models.UniqueConstraint(
                condition=models.Q(item__isnull=True),
                fields=['from_unit', 'to_unit'],
                name='unique_unit_conv_global',
            ),
        ),
        migrations.AddConstraint(
            model_name='unitconversion',
            constraint=models.UniqueConstraint(
                condition=models.Q(item__isnull=False),
                fields=['from_unit', 'to_unit', 'item'],
                name='unique_unit_conv_per_item',
            ),
        ),
    ]
