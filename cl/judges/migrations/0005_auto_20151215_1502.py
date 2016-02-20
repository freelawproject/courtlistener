# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('judges', '0004_auto_20151214_2242'),
    ]

    operations = [
        migrations.AlterField(
            model_name='source',
            name='date_accessed',
            field=models.DateField(help_text=b'The date the data was gathered.', null=True, blank=True),
        ),
    ]
