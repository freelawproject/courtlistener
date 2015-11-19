# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('visualizations', '0005_scotusmap_date_published'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='scotusmap',
            name='subtitle',
        ),
    ]
