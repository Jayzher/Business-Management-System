from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('services', '0008_customerservice_partial_payment_amount'),
    ]

    operations = [
        migrations.AddField(
            model_name='serviceline',
            name='is_scrap',
            field=models.BooleanField(
                default=False,
                help_text='Mark as scrap / waste material — excluded from COGS calculations.',
            ),
        ),
    ]
