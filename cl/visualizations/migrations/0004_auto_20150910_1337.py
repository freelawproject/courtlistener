# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('visualizations', '0003_auto_20150902_1359'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='jsonversion',
            options={'ordering': ['-date_modified']},
        ),
    ]
