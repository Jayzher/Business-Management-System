# Generated migration for MonthlyCashflowSummary

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('cashflow', '0002_add_source_tracking_and_sales_category'),
    ]

    operations = [
        migrations.CreateModel(
            name='MonthlyCashflowSummary',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('year', models.IntegerField(db_index=True)),
                ('month', models.IntegerField(db_index=True)),
                ('capital_sales', models.DecimalField(decimal_places=2, default=0, help_text='Gross profit from sales (revenue - COGS)', max_digits=15)),
                ('capital_other', models.DecimalField(decimal_places=2, default=0, help_text='Other cash-in transactions (capital, investments)', max_digits=15)),
                ('capital_total', models.DecimalField(decimal_places=2, default=0, help_text='Total capital (sales + other cash-in)', max_digits=15)),
                ('expenses_procurement', models.DecimalField(decimal_places=2, default=0, help_text='Total procurement costs (GRN posted amounts)', max_digits=15)),
                ('expenses_operational', models.DecimalField(decimal_places=2, default=0, help_text='Operational expenses (utilities, salaries, etc.)', max_digits=15)),
                ('expenses_other', models.DecimalField(decimal_places=2, default=0, help_text='Other cash-out transactions', max_digits=15)),
                ('expenses_total', models.DecimalField(decimal_places=2, default=0, help_text='Total expenses (procurement + operational + other)', max_digits=15)),
                ('net_profit', models.DecimalField(decimal_places=2, default=0, help_text='Net profit (capital - expenses)', max_digits=15)),
                ('sales_count', models.IntegerField(default=0, help_text='Number of sales transactions')),
                ('procurement_count', models.IntegerField(default=0, help_text='Number of procurement transactions')),
                ('expense_count', models.IntegerField(default=0, help_text='Number of expense records')),
                ('notes', models.TextField(blank=True, default='', help_text='Additional notes or adjustments')),
                ('calculated_by', models.ForeignKey(blank=True, null=True, on_delete=models.SET_NULL, related_name='monthly_summaries_calculated', to=settings.AUTH_USER_MODEL)),
                ('calculated_at', models.DateTimeField(blank=True, null=True)),
            ],
            options={
                'ordering': ['-year', '-month'],
                'unique_together': {('year', 'month')},
                'verbose_name': 'Monthly Cashflow Summary',
                'verbose_name_plural': 'Monthly Cashflow Summaries',
            },
        ),
    ]
