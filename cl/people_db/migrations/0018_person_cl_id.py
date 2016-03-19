# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('people_db', '0017_merge'),
    ]

    operations = [
        migrations.AddField(
            model_name='person',
            name='cl_id',
            field=models.CharField(default=0, help_text=b'A unique identifier for judge, also indicating source of data.', unique=True, max_length=30, db_index=True),
            preserve_default=False,
        ),
    ]
