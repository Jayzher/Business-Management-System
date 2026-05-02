"""Data migration to create the 'Viewer' role."""
from django.db import migrations


def create_viewer_role(apps, schema_editor):
    Role = apps.get_model('accounts', 'Role')
    Role.objects.get_or_create(
        name='Viewer',
        defaults={'description': 'Read-only access to catalog items only.'},
    )


def remove_viewer_role(apps, schema_editor):
    Role = apps.get_model('accounts', 'Role')
    Role.objects.filter(name='Viewer').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0002_initial'),
    ]

    operations = [
        migrations.RunPython(create_viewer_role, remove_viewer_role),
    ]
