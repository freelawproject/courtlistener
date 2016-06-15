# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0020_merge'),
    ]

    operations = [
        migrations.AlterField(
            model_name='docket',
            name='source',
            field=models.SmallIntegerField(help_text=b'contains the source of the Docket.', choices=[(0, b'Default'), (1, b'RECAP'), (2, b'Scraper'), (3, b'RECAP and Scraper'), (4, b'Columbia'), (6, b'Columbia and Scraper'), (5, b'Columbia and RECAP'), (7, b'Columbia, RECAP and Scraper')]),
        ),
    ]
