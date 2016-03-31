# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import datetime
from django.utils.timezone import utc


class Migration(migrations.Migration):

    dependencies = [
        ('alerts', '0002_alert_user'),
    ]

    operations = [
        migrations.AddField(
            model_name='alert',
            name='date_created',
            field=models.DateTimeField(default=datetime.datetime(2015, 8, 8, 1, 24, 7, 658162, tzinfo=utc), help_text=b'The time when this item was created', db_index=True),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='alert',
            name='date_modified',
            field=models.DateTimeField(default=datetime.datetime(2015, 8, 8, 1, 24, 20, 810007, tzinfo=utc), help_text=b'The last moment when the item was modified. A value in year 1750 indicates the value is unknown', db_index=True),
            preserve_default=False,
        ),
    ]
