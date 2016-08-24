# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0033_auto_20160819_1214'),
    ]

    operations = [
        migrations.AlterField(
            model_name='docket',
            name='cause',
            field=models.CharField(help_text=b'The cause for the case.', max_length=500, blank=True),
        ),
    ]
