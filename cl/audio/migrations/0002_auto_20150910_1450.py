# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('audio', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='audio',
            name='date_created',
            field=models.DateTimeField(help_text=b'The original creation date for the item', auto_now_add=True, db_index=True),
        ),
        migrations.AlterField(
            model_name='audio',
            name='date_modified',
            field=models.DateTimeField(help_text=b'The last moment when the item was modified. A value in year 1750 indicates the value is unknown', auto_now=True, db_index=True),
        ),
    ]
