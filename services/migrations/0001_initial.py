from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('catalog', '0001_initial'),
        ('core', '0001_initial'),
        ('warehouses', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='CustomerService',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('service_number', models.CharField(max_length=50, unique=True)),
                ('service_name', models.CharField(max_length=200)),
                ('customer_name', models.CharField(help_text='Customer name (free text)', max_length=200)),
                ('service_date', models.DateField()),
                ('completion_date', models.DateField(blank=True, help_text='Date the service was completed (set when marking as Completed)', null=True)),
                ('address', models.TextField(blank=True, default='')),
                ('notes', models.TextField(blank=True, default='')),
                ('status', models.CharField(
                    choices=[('DRAFT', 'Draft'), ('IN_PROGRESS', 'In Progress'), ('COMPLETED', 'Completed'), ('CANCELLED', 'Cancelled')],
                    db_index=True, default='DRAFT', max_length=20,
                )),
                ('payment_status', models.CharField(
                    choices=[('UNPAID', 'Unpaid'), ('PARTIAL', 'Partially Paid'), ('PAID', 'Paid')],
                    db_index=True, default='UNPAID', max_length=20,
                )),
                ('amount', models.DecimalField(blank=True, decimal_places=2, help_text='Optional manual service fee (overrides product line total)', max_digits=15, null=True)),
                ('posted_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('created_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='services_created', to=settings.AUTH_USER_MODEL)),
                ('invoice', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='customer_services', to='core.invoice')),
                ('posted_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='services_completed', to=settings.AUTH_USER_MODEL)),
                ('warehouse', models.ForeignKey(blank=True, help_text='Warehouse to deduct parts from when completed', null=True, on_delete=django.db.models.deletion.PROTECT, related_name='customer_services', to='warehouses.warehouse')),
            ],
            options={
                'verbose_name': 'Customer Service',
                'verbose_name_plural': 'Customer Services',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='ServiceLine',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('qty', models.DecimalField(decimal_places=4, max_digits=15)),
                ('unit_price', models.DecimalField(decimal_places=4, default=0, help_text='Auto-filled from Item catalog selling price', max_digits=15)),
                ('notes', models.TextField(blank=True, default='')),
                ('item', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='catalog.item')),
                ('location', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to='warehouses.location')),
                ('service', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='lines', to='services.customerservice')),
                ('unit', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='catalog.unit')),
            ],
        ),
    ]
