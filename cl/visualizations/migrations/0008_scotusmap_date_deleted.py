# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('visualizations', '0007_auto_20151119_1048'),
    ]

    operations = [
        migrations.AddField(
            model_name='scotusmap',
            name='date_deleted',
            field=models.DateTimeField(help_text=b'The moment when the visualization was last deleted', null=True, db_index=True, blank=True),
        ),
    ]
