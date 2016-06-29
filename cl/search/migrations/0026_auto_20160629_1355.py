# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0025_add_more_courts'),
    ]

    operations = [
        migrations.AlterField(
            model_name='court',
            name='url',
            field=models.URLField(help_text=b'the homepage for each court or the closest thing thereto', max_length=500, blank=True),
        ),
    ]
