# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('people_db', '0033_merge'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='attorney',
            name='date_sourced',
        ),
    ]
