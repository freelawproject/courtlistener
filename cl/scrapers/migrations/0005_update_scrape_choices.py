# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('scrapers', '0004_auto_20161112_2154'),
    ]

    operations = [
        migrations.AlterField(
            model_name='recaplog',
            name='status',
            field=models.SmallIntegerField(help_text=b'The current status of the RECAP scrape.', choices=[(1, b'Scrape Completed Successfully'), (2, b'Scrape currently in progress'), (4, b'Getting list of new content from archive server'), (5, b'Successfully got the change list.'), (6, b'Getting and merging items from server'), (3, b'Scrape Failed')]),
        ),
    ]
