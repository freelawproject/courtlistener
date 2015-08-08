# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import datetime
from django.utils.timezone import utc


class Migration(migrations.Migration):

    dependencies = [
        ('favorites', '0003_favorite_user'),
    ]

    operations = [
        migrations.AddField(
            model_name='favorite',
            name='date_created',
            field=models.DateTimeField(default=datetime.datetime(2015, 8, 8, 1, 24, 31, 721669, tzinfo=utc), help_text=b'The original creation date for the item', db_index=True),
            preserve_default=False,
        ),
    ]
