from django.db import migrations


def seed_responsibility(apps, schema_editor):
    Responsibility = apps.get_model('crm', 'Responsibility')
    for name in ['Prefequity', 'Intermediary']:
        Responsibility.objects.get_or_create(name=name)


class Migration(migrations.Migration):

    dependencies = [
        ('crm', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(seed_responsibility, migrations.RunPython.noop),
    ]

