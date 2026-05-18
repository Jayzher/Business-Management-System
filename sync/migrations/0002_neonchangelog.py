"""
Add NeonChangeLog model — sequential change log stored on Neon (PostgreSQL).

This table records every write to Neon so that local servers can catch up
on changes made by other devices while they were offline.
"""

from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('sync', '0001_add_sync_outbox'),
    ]

    operations = [
        migrations.CreateModel(
            name='NeonChangeLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('action', models.CharField(choices=[('upsert', 'Upsert'), ('delete', 'Delete')], max_length=10)),
                ('db_table', models.CharField(db_index=True, max_length=100)),
                ('app_label', models.CharField(max_length=50)),
                ('model_name', models.CharField(max_length=50)),
                ('row_pk', models.BigIntegerField()),
                ('row_data', models.JSONField(blank=True, null=True)),
                ('created_at', models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ('source_device', models.CharField(blank=True, default='', help_text='Identifier of the device/server that made the change.', max_length=100)),
            ],
            options={
                'ordering': ['id'],
                'indexes': [
                    models.Index(fields=['db_table', 'created_at'], name='sync_neoncha_db_tabl_idx'),
                    models.Index(fields=['created_at'], name='sync_neoncha_created_idx'),
                ],
            },
        ),
    ]
