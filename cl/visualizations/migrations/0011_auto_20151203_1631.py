# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('visualizations', '0010_auto_20151125_1041'),
    ]

    operations = [
        migrations.AlterField(
            model_name='scotusmap',
            name='date_published',
            field=models.DateTimeField(help_text=b'The moment when the visualization was first shared', null=True, db_index=True, blank=True),
        ),
        migrations.AlterField(
            model_name='scotusmap',
            name='published',
            field=models.BooleanField(default=False, help_text=b'Whether the visualization has been shared.'),
        ),
    ]
