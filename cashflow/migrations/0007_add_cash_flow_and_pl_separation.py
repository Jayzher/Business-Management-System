# Generated migration for cash flow and P&L separation

from django.db import migrations, models
from decimal import Decimal


class Migration(migrations.Migration):

    dependencies = [
        ('cashflow', '0006_add_inventory_asset_tracking'),
    ]

    operations = [
        # Cash Flow Statement Fields (Actual Cash Movement)
        migrations.AddField(
            model_name='monthlycashflowsummary',
            name='cash_opening',
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text='Actual cash balance at start of month',
                max_digits=15
            ),
        ),
        migrations.AddField(
            model_name='monthlycashflowsummary',
            name='cash_closing',
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text='Actual cash balance at end of month',
                max_digits=15
            ),
        ),
        migrations.AddField(
            model_name='monthlycashflowsummary',
            name='cash_from_customers',
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text='Actual cash received from customers (payments)',
                max_digits=15
            ),
        ),
        migrations.AddField(
            model_name='monthlycashflowsummary',
            name='cash_to_suppliers',
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text='Actual cash paid to suppliers',
                max_digits=15
            ),
        ),
        migrations.AddField(
            model_name='monthlycashflowsummary',
            name='operating_cash_flow',
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text='Net cash from operating activities',
                max_digits=15
            ),
        ),
        
        # Accounts Receivable & Payable
        migrations.AddField(
            model_name='monthlycashflowsummary',
            name='accounts_receivable_opening',
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text='Unpaid invoices at start of month',
                max_digits=15
            ),
        ),
        migrations.AddField(
            model_name='monthlycashflowsummary',
            name='accounts_receivable_closing',
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text='Unpaid invoices at end of month',
                max_digits=15
            ),
        ),
        migrations.AddField(
            model_name='monthlycashflowsummary',
            name='accounts_payable_opening',
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text='Unpaid bills at start of month',
                max_digits=15
            ),
        ),
        migrations.AddField(
            model_name='monthlycashflowsummary',
            name='accounts_payable_closing',
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text='Unpaid bills at end of month',
                max_digits=15
            ),
        ),
        
        # P&L Statement Fields (Accrual Basis)
        migrations.AddField(
            model_name='monthlycashflowsummary',
            name='revenue_accrual',
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text='Total revenue earned (invoiced) this month',
                max_digits=15
            ),
        ),
        migrations.AddField(
            model_name='monthlycashflowsummary',
            name='gross_profit',
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text='Revenue - COGS',
                max_digits=15
            ),
        ),
        migrations.AddField(
            model_name='monthlycashflowsummary',
            name='gross_margin_pct',
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text='Gross profit margin percentage',
                max_digits=5
            ),
        ),
        
        # Performance Metrics
        migrations.AddField(
            model_name='monthlycashflowsummary',
            name='collection_rate_pct',
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text='Percentage of invoices collected',
                max_digits=5
            ),
        ),
        migrations.AddField(
            model_name='monthlycashflowsummary',
            name='days_sales_outstanding',
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text='Average days to collect payment',
                max_digits=8
            ),
        ),
        migrations.AddField(
            model_name='monthlycashflowsummary',
            name='inventory_turnover',
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text='How many times inventory sold in month',
                max_digits=8
            ),
        ),
    ]
