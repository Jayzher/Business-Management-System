import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('sync', '0003_rename_sync_neoncha_db_tabl_idx_sync_neonch_db_tabl_773f80_idx_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='ChangelogReplayFailure',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('changelog_id', models.BigIntegerField(db_index=True, help_text='The NeonChangeLog id that last failed for this row.')),
                ('action', models.CharField(choices=[('upsert', 'Upsert'), ('delete', 'Delete')], max_length=10)),
                ('db_table', models.CharField(db_index=True, max_length=100)),
                ('app_label', models.CharField(max_length=50)),
                ('model_name', models.CharField(max_length=50)),
                ('row_pk', models.BigIntegerField()),
                ('error_message', models.TextField(blank=True, default='')),
                ('attempts', models.IntegerField(default=1)),
                ('first_failed_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('last_failed_at', models.DateTimeField(default=django.utils.timezone.now)),
            ],
            options={
                'ordering': ['-last_failed_at'],
            },
        ),
        migrations.AddConstraint(
            model_name='changelogreplayfailure',
            constraint=models.UniqueConstraint(fields=('db_table', 'row_pk'), name='sync_changelogfail_table_pk_uniq'),
        ),
    ]
