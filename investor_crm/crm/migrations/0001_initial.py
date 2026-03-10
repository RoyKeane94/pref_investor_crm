from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name='Responsibility',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255, unique=True)),
            ],
        ),
        migrations.CreateModel(
            name='Investor',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255)),
                ('principal_contact', models.CharField(blank=True, max_length=255)),
                ('website', models.URLField(blank=True)),
                ('status', models.CharField(choices=[('confirmed', 'Confirmed'), ('potential_sma', 'Potential SMA'), ('target_fund_iii', 'Target for Fund III')], default='target_fund_iii', max_length=20)),
                ('ticket_size', models.DecimalField(blank=True, decimal_places=1, max_digits=10, null=True)),
                ('vdr_access', models.BooleanField(default=False)),
                ('vdr_access_date', models.DateField(blank=True, null=True)),
                ('office', models.CharField(blank=True, max_length=255)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('responsibility', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='crm.responsibility')),
            ],
            options={
                'ordering': ['name'],
            },
        ),
        migrations.CreateModel(
            name='Contact',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255)),
                ('role', models.CharField(blank=True, max_length=255)),
                ('email', models.EmailField(blank=True, max_length=254)),
                ('phone', models.CharField(blank=True, max_length=50)),
                ('investor', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='contacts', to='crm.investor')),
            ],
        ),
        migrations.CreateModel(
            name='CallLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateField()),
                ('contact_name_override', models.CharField(blank=True, max_length=255)),
                ('notes', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('contact', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='crm.contact')),
                ('investor', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='call_logs', to='crm.investor')),
            ],
            options={
                'ordering': ['-date', '-created_at'],
            },
        ),
        migrations.CreateModel(
            name='EmailLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateField()),
                ('contact_name_override', models.CharField(blank=True, max_length=255)),
                ('subject', models.CharField(blank=True, max_length=500)),
                ('direction', models.CharField(choices=[('inbound', 'Inbound'), ('outbound', 'Outbound')], max_length=10)),
                ('notes', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('contact', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='crm.contact')),
                ('investor', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='email_logs', to='crm.investor')),
            ],
            options={
                'ordering': ['-date', '-created_at'],
            },
        ),
        migrations.CreateModel(
            name='OtherCommitment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('fund', models.CharField(max_length=255)),
                ('amount', models.DecimalField(blank=True, decimal_places=1, max_digits=10, null=True)),
                ('date', models.DateField(blank=True, null=True)),
                ('notes', models.TextField(blank=True)),
                ('investor', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='commitments', to='crm.investor')),
            ],
        ),
        migrations.CreateModel(
            name='InfoLink',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=255)),
                ('detail', models.TextField(blank=True)),
                ('link', models.URLField(blank=True)),
                ('investor', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='info_links', to='crm.investor')),
            ],
        ),
        migrations.CreateModel(
            name='CoInvestment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255)),
                ('size', models.DecimalField(blank=True, decimal_places=1, max_digits=10, null=True)),
                ('decision', models.CharField(choices=[('pending', 'Pending'), ('committed', 'Committed'), ('passed', 'Passed')], default='pending', max_length=10)),
                ('date', models.DateField(blank=True, null=True)),
                ('investor', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='co_investments', to='crm.investor')),
            ],
            options={
                'ordering': ['-date'],
            },
        ),
        migrations.CreateModel(
            name='Reminder',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('description', models.CharField(max_length=500)),
                ('due_date', models.DateField()),
                ('is_done', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('investor', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='reminders', to='crm.investor')),
            ],
            options={
                'ordering': ['due_date'],
            },
        ),
    ]

