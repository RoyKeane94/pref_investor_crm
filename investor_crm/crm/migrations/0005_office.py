# Migration to replace Investor.office CharField with Office FK (data-preserving)

import django.db.models.deletion
from django.db import migrations, models


def migrate_office_to_model(apps, schema_editor):
    Investor = apps.get_model('crm', 'Investor')
    Office = apps.get_model('crm', 'Office')
    for inv in Investor.objects.all():
        old_office = getattr(inv, 'office', None)
        if old_office and str(old_office).strip():
            office, _ = Office.objects.get_or_create(name=str(old_office).strip())
            inv.office_new = office
            inv.save(update_fields=['office_new'])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('crm', '0004_intermediary_investor_intermediary'),
    ]

    operations = [
        migrations.CreateModel(
            name='Office',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255, unique=True)),
            ],
        ),
        migrations.AddField(
            model_name='investor',
            name='office_new',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='investors',
                to='crm.office',
            ),
        ),
        migrations.RunPython(migrate_office_to_model, noop),
        migrations.RemoveField(
            model_name='investor',
            name='office',
        ),
        migrations.RenameField(
            model_name='investor',
            old_name='office_new',
            new_name='office',
        ),
    ]
