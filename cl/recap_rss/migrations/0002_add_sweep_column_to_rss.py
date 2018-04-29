# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('recap_rss', '0001_add_rss_feed_models'),
    ]

    operations = [
        migrations.AddField(
            model_name='rssfeedstatus',
            name='is_sweep',
            field=models.BooleanField(default=False, help_text=b'Whether this object is tracking the progress of a sweep or a partial crawl.'),
        ),
    ]
