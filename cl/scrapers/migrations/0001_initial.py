# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='ErrorLog',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('log_time', models.DateTimeField(auto_now_add=True, verbose_name=b'the exact date and time of the error')),
                ('log_level', models.CharField(verbose_name=b'the loglevel of the error encountered', max_length=15, editable=False)),
                ('message', models.TextField(verbose_name=b'the message produced in the log', editable=False, blank=True)),
                ('court', models.ForeignKey(verbose_name=b'the court where the error occurred', to='search.Court')),
            ],
        ),
        migrations.CreateModel(
            name='UrlHash',
            fields=[
                ('id', models.CharField(verbose_name=b'the ID of the item that is hashed', max_length=5000, serialize=False, editable=False, primary_key=True)),
                ('sha1', models.CharField(verbose_name=b'a SHA1 corresponding to the item', max_length=40, editable=False)),
            ],
            options={
                'verbose_name_plural': 'URL Hashes',
            },
        ),
    ]
