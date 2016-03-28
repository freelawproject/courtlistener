# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0003_recap'),
    ]

    operations = [
        migrations.AlterField(
            model_name='docket',
            name='source',
            field=models.SmallIntegerField(help_text=b'contains the source of the Docket.', choices=[(0, b'Default'), (1, b'RECAP'), (2, b'Scraper')]),
        ),
    ]
