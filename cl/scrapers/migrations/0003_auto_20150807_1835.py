# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import datetime
from django.utils.timezone import utc


class Migration(migrations.Migration):

    dependencies = [
        ('scrapers', '0002_auto_20150807_1826'),
    ]

    operations = [
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
        migrations.DeleteModel(
            name='urlToHash',
        ),
        migrations.AlterField(
            model_name='errorlog',
            name='log_time',
            field=models.DateTimeField(default=datetime.datetime(2015, 8, 8, 1, 35, 6, 644344, tzinfo=utc), verbose_name=b'the exact date and time of the error', auto_now_add=True),
            preserve_default=False,
        ),
    ]
