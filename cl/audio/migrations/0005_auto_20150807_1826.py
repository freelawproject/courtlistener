# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import datetime
from django.utils.timezone import utc


class Migration(migrations.Migration):

    dependencies = [
        ('audio', '0004_auto_20150803_1511'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='audio',
            options={'ordering': ['-date_created'], 'verbose_name_plural': 'Audio Files'},
        ),
        migrations.RemoveField(
            model_name='audio',
            name='time_retrieved',
        ),
        migrations.AddField(
            model_name='audio',
            name='date_created',
            field=models.DateTimeField(default=datetime.datetime(2015, 8, 8, 1, 24, 26, 633886, tzinfo=utc), help_text=b'The original creation date for the item', db_index=True),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='audio',
            name='date_modified',
            field=models.DateTimeField(help_text=b'The last moment when the item was modified. A value in year 1750 indicates the value is unknown', db_index=True),
        ),
    ]
