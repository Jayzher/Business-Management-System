from decimal import Decimal
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('services', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='customerservice',
            name='service_fee',
            field=models.DecimalField(
                blank=True, decimal_places=2, default=None, max_digits=15, null=True,
                help_text='Service / labor charge added on top of product & material lines.',
            ),
        ),
        migrations.AddField(
            model_name='customerservice',
            name='discount_type',
            field=models.CharField(
                choices=[('FIXED', 'Fixed Amount (₱)'), ('PERCENT', 'Percentage (%)')],
                default='FIXED', max_length=10,
            ),
        ),
        migrations.AddField(
            model_name='customerservice',
            name='discount_value',
            field=models.DecimalField(
                decimal_places=2, default=Decimal('0'), max_digits=15,
                help_text='Discount: fixed ₱ amount or percentage of subtotal.',
            ),
        ),
        migrations.CreateModel(
            name='ServiceOtherMaterial',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('item_name', models.CharField(help_text='Material or supply description', max_length=200)),
                ('qty', models.DecimalField(decimal_places=4, max_digits=15)),
                ('unit_price', models.DecimalField(
                    decimal_places=4, default=0, max_digits=15,
                    help_text='Price charged per unit',
                )),
                ('vendor', models.CharField(blank=True, default='', max_length=200)),
                ('notes', models.CharField(blank=True, default='', max_length=255)),
                ('service', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='other_materials',
                    to='services.customerservice',
                )),
            ],
        ),
    ]
