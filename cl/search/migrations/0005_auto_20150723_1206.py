# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0004_auto_20150713_1421'),
    ]

    operations = [
        migrations.AlterField(
            model_name='opinioncluster',
            name='date_filed',
            field=models.DateField(help_text=b'The date filed by the court', db_index=True),
        ),
    ]
