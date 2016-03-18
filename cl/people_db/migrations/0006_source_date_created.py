# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import datetime
from django.utils.timezone import utc


class Migration(migrations.Migration):

    dependencies = [
        ('people_db', '0005_auto_20160226_0757'),
    ]

    operations = [
        migrations.AddField(
            model_name='source',
            name='date_created',
            field=models.DateTimeField(default=datetime.datetime(2016, 2, 26, 20, 23, 8, 71180, tzinfo=utc), auto_now_add=True, help_text=b'The original creation date for the item', db_index=True),
            preserve_default=False,
        ),
    ]
