# Generated by Django 3.1.7 on 2021-05-28 19:35

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('search', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='RealTimeQueue',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date_modified', models.DateTimeField(auto_now=True, db_index=True, help_text='the last moment when the item was modified')),
                ('item_type', models.CharField(choices=[('o', 'Opinions'), ('r', 'RECAP'), ('d', 'RECAP Dockets'), ('oa', 'Oral Arguments'), ('p', 'People')], db_index=True, help_text='the type of item this is, one of: o (Opinions), r (RECAP), d (RECAP Dockets), oa (Oral Arguments), p (People)', max_length=3)),
                ('item_pk', models.IntegerField(help_text='the pk of the item')),
            ],
        ),
        migrations.CreateModel(
            name='Alert',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date_created', models.DateTimeField(auto_now_add=True, db_index=True, help_text='The moment when the item was created.')),
                ('date_modified', models.DateTimeField(auto_now=True, db_index=True, help_text='The last moment when the item was modified. A value in year 1750 indicates the value is unknown')),
                ('date_last_hit', models.DateTimeField(blank=True, null=True, verbose_name='time of last trigger')),
                ('name', models.CharField(max_length=75, verbose_name='a name for the alert')),
                ('query', models.CharField(max_length=2500, verbose_name='the text of an alert created by a user')),
                ('rate', models.CharField(choices=[('rt', 'Real Time'), ('dly', 'Daily'), ('wly', 'Weekly'), ('mly', 'Monthly'), ('off', 'Off')], max_length=10, verbose_name='the rate chosen by the user for the alert')),
                ('secret_key', models.CharField(max_length=40, verbose_name='A key to be used in links to access the alert without having to log in. Can be used for a variety of purposes.')),
                ('user', models.ForeignKey(help_text='The user that created the item', on_delete=django.db.models.deletion.CASCADE, related_name='alerts', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['rate', 'query'],
            },
        ),
        migrations.CreateModel(
            name='DocketSubscription',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date_created', models.DateTimeField(auto_now_add=True, db_index=True, help_text='The moment when the item was created.')),
                ('date_modified', models.DateTimeField(auto_now=True, db_index=True, help_text='The last moment when the item was modified. A value in year 1750 indicates the value is unknown')),
                ('date_last_hit', models.DateTimeField(blank=True, help_text='The last date on which an email was received for the case.', null=True)),
                ('secret_key', models.CharField(help_text='A key to be used in links to access the alert without having to log in. Can be used for a variety of purposes.', max_length=40)),
                ('docket', models.ForeignKey(help_text='The docket that we are subscribed to.', on_delete=django.db.models.deletion.CASCADE, related_name='subscriptions', to='search.docket')),
                ('user', models.ForeignKey(help_text='The user that is subscribed to the docket.', on_delete=django.db.models.deletion.CASCADE, related_name='subscriptions', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'unique_together': {('docket', 'user')},
            },
        ),
        migrations.CreateModel(
            name='DocketAlert',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date_created', models.DateTimeField(auto_now_add=True, db_index=True, help_text='The time when this item was created')),
                ('date_last_hit', models.DateTimeField(blank=True, null=True, verbose_name='time of last trigger')),
                ('secret_key', models.CharField(max_length=40, verbose_name='A key to be used in links to access the alert without having to log in. Can be used for a variety of purposes.')),
                ('docket', models.ForeignKey(help_text='The docket that we are subscribed to.', on_delete=django.db.models.deletion.CASCADE, related_name='alerts', to='search.docket')),
                ('user', models.ForeignKey(help_text='The user that is subscribed to the docket.', on_delete=django.db.models.deletion.CASCADE, related_name='docket_alerts', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'unique_together': {('docket', 'user')},
            },
        ),
    ]
