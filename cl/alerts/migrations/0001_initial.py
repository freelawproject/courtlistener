# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Alert',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('name', models.CharField(max_length=75, verbose_name=b'a name for the alert')),
                ('query', models.CharField(max_length=2500, verbose_name=b'the text of an alert created by a user')),
                ('rate', models.CharField(max_length=10, verbose_name=b'the rate chosen by the user for the alert', choices=[(b'rt', b'Real Time'), (b'dly', b'Daily'), (b'wly', b'Weekly'), (b'mly', b'Monthly'), (b'off', b'Off')])),
                ('always_send_email', models.BooleanField(default=False, verbose_name=b'Always send an alert?')),
                ('date_last_hit', models.DateTimeField(null=True, verbose_name=b'time of last trigger', blank=True)),
            ],
            options={
                'ordering': ['rate', 'query'],
            },
        ),
        migrations.CreateModel(
            name='RealTimeQueue',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('date_modified', models.DateTimeField(help_text=b'the last moment when the item was modified', auto_now=True, db_index=True)),
                ('item_type', models.CharField(help_text=b'the type of item this is, one of: o (Opinion), oa (Oral Argument)', max_length=3, db_index=True, choices=[(b'o', b'Opinion'), (b'oa', b'Oral Argument')])),
                ('item_pk', models.IntegerField(help_text=b'the pk of the item')),
            ],
        ),
    ]
