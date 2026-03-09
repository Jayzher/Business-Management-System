from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pricing', '0002_add_customer_price_catalog'),
    ]

    operations = [
        migrations.AddField(
            model_name='customerpricecatalog',
            name='end_date',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='customerpricecatalog',
            name='start_date',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AlterModelOptions(
            name='customerpricecatalog',
            options={'ordering': ['customer__name', 'name', 'start_date']},
        ),
    ]
