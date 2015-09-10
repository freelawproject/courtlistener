# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('alerts', '0003_auto_20150807_1826'),
    ]

    operations = [
        migrations.AlterField(
            model_name='alert',
            name='date_created',
            field=models.DateTimeField(help_text=b'The time when this item was created', auto_now_add=True, db_index=True),
        ),
        migrations.AlterField(
            model_name='alert',
            name='date_modified',
            field=models.DateTimeField(help_text=b'The last moment when the item was modified. A value in year 1750 indicates the value is unknown', auto_now=True, db_index=True),
        ),
    ]
