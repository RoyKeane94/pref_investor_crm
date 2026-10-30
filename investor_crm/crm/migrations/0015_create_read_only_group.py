from django.db import migrations


def create_read_only_group(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    Group.objects.get_or_create(name='Read Only')


def remove_read_only_group(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    Group.objects.filter(name='Read Only').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('crm', '0014_contact_is_ex'),
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.RunPython(create_read_only_group, remove_read_only_group),
    ]
