# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import datetime
from django.utils.timezone import utc


class Migration(migrations.Migration):

    dependencies = [
        ('judges', '0005_auto_20150807_1444'),
    ]

    operations = [
        migrations.AddField(
            model_name='abarating',
            name='date_created',
            field=models.DateTimeField(default=datetime.datetime(2015, 8, 8, 1, 24, 36, 905555, tzinfo=utc), auto_now_add=True, help_text=b'The original creation date for the item', db_index=True),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='career',
            name='date_created',
            field=models.DateTimeField(default=datetime.datetime(2015, 8, 8, 1, 24, 43, 705778, tzinfo=utc), auto_now_add=True, help_text=b'The original creation date for the item', db_index=True),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='education',
            name='date_created',
            field=models.DateTimeField(default=datetime.datetime(2015, 8, 8, 1, 24, 48, 793687, tzinfo=utc), auto_now_add=True, help_text=b'The original creation date for the item', db_index=True),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='politicalaffiliation',
            name='date_created',
            field=models.DateTimeField(default=datetime.datetime(2015, 8, 8, 1, 24, 55, 977607, tzinfo=utc), auto_now_add=True, help_text=b'The original creation date for the item', db_index=True),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='position',
            name='date_created',
            field=models.DateTimeField(default=datetime.datetime(2015, 8, 8, 1, 25, 0, 489618, tzinfo=utc), auto_now_add=True, help_text=b'The time when this item was created', db_index=True),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='retentionevent',
            name='date_created',
            field=models.DateTimeField(default=datetime.datetime(2015, 8, 8, 1, 25, 3, 817247, tzinfo=utc), auto_now_add=True, help_text=b'The original creation date for the item', db_index=True),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='school',
            name='date_created',
            field=models.DateTimeField(default=datetime.datetime(2015, 8, 8, 1, 25, 8, 633606, tzinfo=utc), auto_now_add=True, help_text=b'The original creation date for the item', db_index=True),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='school',
            name='date_modified',
            field=models.DateTimeField(default=datetime.datetime(2015, 8, 8, 1, 25, 16, 457544, tzinfo=utc), auto_now=True, help_text=b'The last moment when the item was modified', db_index=True),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='source',
            name='date_modified',
            field=models.DateTimeField(default=datetime.datetime(2015, 8, 8, 1, 25, 20, 841497, tzinfo=utc), auto_now=True, help_text=b'The last moment when the item was modified', db_index=True),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='title',
            name='date_created',
            field=models.DateTimeField(default=datetime.datetime(2015, 8, 8, 1, 25, 27, 96993, tzinfo=utc), auto_now_add=True, help_text=b'The original creation date for the item', db_index=True),
            preserve_default=False,
        ),
    ]
