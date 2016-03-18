# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('people_db', '0006_source_date_created'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='school',
            name='ope_id',
        ),
        migrations.RemoveField(
            model_name='school',
            name='unit_id',
        ),
    ]
