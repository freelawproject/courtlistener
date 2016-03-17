# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0013_auto_20160311_1639'),
    ]

    operations = [
        migrations.AddField(
            model_name='opinionscited',
            name='depth',
            field=models.IntegerField(default=1, help_text=b'The number of times the cited opinion was cited in the citing opinion', db_index=True),
        ),
        migrations.AddField(
            model_name='opinionscited',
            name='quoted',
            field=models.BooleanField(default=False, help_text=b'Equals true if previous case was quoted directly', db_index=True),
        ),
    ]
