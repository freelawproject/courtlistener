# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0002_load_initial_data'),
    ]

    operations = [
        migrations.AlterField(
            model_name='opinion',
            name='type',
            field=models.CharField(max_length=20, choices=[
                (b'010combined', b'Combined Opinion'),
                (b'020lead', b'Lead Opinion'),
                (b'030concurrence', b'Concurrence'),
                (b'040dissent', b'Dissent')]),
        ),
    ]
