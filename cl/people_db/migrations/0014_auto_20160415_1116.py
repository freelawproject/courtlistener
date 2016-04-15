# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('people_db', '0013_auto_20160415_1041'),
    ]

    operations = [
        migrations.AlterField(
            model_name='person',
            name='religion',
            field=models.CharField(max_length=30, blank=True),
        ),
    ]
