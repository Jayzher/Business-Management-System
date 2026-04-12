# Generated migration for adding opening and closing balance fields

from django.db import migrations, models
from decimal import Decimal


class Migration(migrations.Migration):
    atomic = False  # Disable atomic transactions to allow FK pragma changes

    dependencies = [
        ('cashflow', '0003_monthlycashflowsummary'),
    ]

    operations = [
        migrations.RunSQL(
            sql='PRAGMA foreign_keys = OFF;',
            reverse_sql='PRAGMA foreign_keys = ON;',
        ),
        migrations.AddField(
            model_name='monthlycashflowsummary',
            name='opening_balance',
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text='Opening balance carried from previous month',
                max_digits=15
            ),
        ),
        migrations.AddField(
            model_name='monthlycashflowsummary',
            name='closing_balance',
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text='Closing balance (opening + net cash flow)',
                max_digits=15
            ),
        ),
        migrations.AddField(
            model_name='monthlycashflowsummary',
            name='total_inflow',
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text='Total cash inflow (capital_total)',
                max_digits=15
            ),
        ),
        migrations.AddField(
            model_name='monthlycashflowsummary',
            name='total_outflow',
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text='Total cash outflow (expenses_total)',
                max_digits=15
            ),
        ),
        migrations.AddField(
            model_name='monthlycashflowsummary',
            name='net_cash_flow',
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text='Net cash flow (total_inflow - total_outflow)',
                max_digits=15
            ),
        ),
        migrations.RunSQL(
            sql='PRAGMA foreign_keys = ON;',
            reverse_sql='PRAGMA foreign_keys = OFF;',
        ),
    ]
