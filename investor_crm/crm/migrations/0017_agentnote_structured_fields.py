from django.db import migrations, models


def migrate_other_to_investment(apps, schema_editor):
    AgentNote = apps.get_model('crm', 'AgentNote')
    AgentNote.objects.filter(note_type='other').update(note_type='investment')


def migrate_investment_to_other(apps, schema_editor):
    AgentNote = apps.get_model('crm', 'AgentNote')
    AgentNote.objects.filter(note_type='investment').update(note_type='other')


class Migration(migrations.Migration):

    dependencies = [
        ('crm', '0016_agent_note'),
    ]

    operations = [
        migrations.AddField(
            model_name='agentnote',
            name='title',
            field=models.CharField(
                blank=True,
                help_text='Headline or short label',
                max_length=500,
            ),
        ),
        migrations.AddField(
            model_name='agentnote',
            name='link',
            field=models.URLField(
                blank=True,
                help_text='Source URL (news article, press release, etc.)',
            ),
        ),
        migrations.AlterField(
            model_name='agentnote',
            name='body',
            field=models.TextField(blank=True, help_text='Summary / detail'),
        ),
        migrations.RunPython(migrate_other_to_investment, migrate_investment_to_other),
        migrations.AlterField(
            model_name='agentnote',
            name='note_type',
            field=models.CharField(
                choices=[
                    ('news', 'News'),
                    ('person_change', 'Personnel change'),
                    ('investment', 'Investment'),
                ],
                default='news',
                max_length=20,
            ),
        ),
    ]
