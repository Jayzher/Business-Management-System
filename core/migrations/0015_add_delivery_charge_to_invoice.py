# Generated migration

from django.db import migrations, models
from decimal import Decimal


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0007_invoice_paid_date'),
    ]

    operations = [
        migrations.AddField(
            model_name='invoice',
            name='delivery_charge',
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text='Delivery/shipping charge added to the invoice total.',
                max_digits=15
            ),
        ),
    ]
