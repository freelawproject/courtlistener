# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('judges', '0003_load_initial_data'),
    ]

    operations = [
        migrations.AlterField(
            model_name='title',
            name='date_granularity_end',
            field=models.CharField(blank=True, max_length=15, choices=[(b'%Y', b'Year'), (b'%Y-%m', b'Month'), (b'%Y-%m-%d', b'Day')]),
        ),
        migrations.AlterField(
            model_name='title',
            name='date_granularity_start',
            field=models.CharField(blank=True, max_length=15, choices=[(b'%Y', b'Year'), (b'%Y-%m', b'Month'), (b'%Y-%m-%d', b'Day')]),
        ),
    ]
