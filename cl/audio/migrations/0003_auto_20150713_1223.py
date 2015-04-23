# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('audio', '0002_auto_20150708_1801'),
    ]

    operations = [
        migrations.AlterField(
            model_name='audio',
            name='date_modified',
            field=models.DateTimeField(help_text=b'The last moment when the item was modified. A value in year 1750 indicates the value is unknown', editable=False, db_index=True),
        ),
        migrations.AlterField(
            model_name='audio',
            name='time_retrieved',
            field=models.DateTimeField(help_text=b'The original creation date for the item', editable=False, db_index=True),
        ),
    ]
