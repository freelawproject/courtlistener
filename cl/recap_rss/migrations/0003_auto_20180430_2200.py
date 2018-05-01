# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('recap_rss', '0002_add_sweep_column_to_rss'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='rssfeedstatus',
            options={'verbose_name_plural': 'RSS Feed Statuses'},
        ),
    ]
