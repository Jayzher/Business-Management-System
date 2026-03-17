from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0005_invoice_is_void'),
    ]

    operations = [
        migrations.AddField(
            model_name='invoice',
            name='grand_total_cogs',
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text='Computed COGS for this invoice (synced via sync_invoice_cogs command).',
                max_digits=15,
            ),
        ),
    ]
