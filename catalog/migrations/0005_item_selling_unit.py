from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0004_alter_item_item_type'),
    ]

    operations = [
        migrations.AddField(
            model_name='item',
            name='selling_unit',
            field=models.ForeignKey(
                blank=True,
                help_text='Default unit used when selling this item. Falls back to the base unit when not set.',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='selling_items',
                to='catalog.unit',
            ),
        ),
    ]
