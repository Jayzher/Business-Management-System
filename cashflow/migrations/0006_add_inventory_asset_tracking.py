# Generated migration for inventory asset tracking

from django.db import migrations, models
from decimal import Decimal


class Migration(migrations.Migration):

    dependencies = [
        ('cashflow', '0005_alter_monthlycashflowsummary_net_profit'),
    ]

    operations = [
        migrations.AddField(
            model_name='monthlycashflowsummary',
            name='inventory_value_opening',
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text='Inventory asset value at start of month (cost basis)',
                max_digits=15
            ),
        ),
        migrations.AddField(
            model_name='monthlycashflowsummary',
            name='inventory_value_closing',
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text='Inventory asset value at end of month (cost basis)',
                max_digits=15
            ),
        ),
        migrations.AddField(
            model_name='monthlycashflowsummary',
            name='inventory_purchased',
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text='Total inventory purchased this month (procurement costs)',
                max_digits=15
            ),
        ),
        migrations.AddField(
            model_name='monthlycashflowsummary',
            name='cogs_actual',
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text='Actual COGS from sales/services this month',
                max_digits=15
            ),
        ),
        migrations.AlterField(
            model_name='monthlycashflowsummary',
            name='expenses_procurement',
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text='DEPRECATED: Use cogs_actual instead. Procurement is asset conversion, not expense.',
                max_digits=15
            ),
        ),
        migrations.AlterField(
            model_name='monthlycashflowsummary',
            name='opening_balance',
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text='Opening cash + inventory assets from previous month',
                max_digits=15
            ),
        ),
        migrations.AlterField(
            model_name='monthlycashflowsummary',
            name='closing_balance',
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text='Closing cash + inventory assets (opening + net cash flow)',
                max_digits=15
            ),
        ),
    ]
