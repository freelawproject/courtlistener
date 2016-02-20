# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('visualizations', '0004_auto_20150910_1337'),
    ]

    operations = [
        migrations.AddField(
            model_name='scotusmap',
            name='date_published',
            field=models.DateTimeField(help_text=b'The moment when the visualization was first published', null=True, db_index=True, blank=True),
        ),
    ]
