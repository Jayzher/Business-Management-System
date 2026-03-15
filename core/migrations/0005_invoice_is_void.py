from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0004_supplymovement_batch_number_supplymovement_reference'),
    ]

    operations = [
        migrations.AddField(
            model_name='invoice',
            name='is_void',
            field=models.BooleanField(
                default=False,
                help_text='Set True when the linked delivery/pickup is cancelled after posting.',
            ),
        ),
        migrations.AddField(
            model_name='invoice',
            name='void_reason',
            field=models.CharField(blank=True, default='', max_length=255),
        ),
    ]
