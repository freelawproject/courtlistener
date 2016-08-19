# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0032_auto_20160819_1209'),
    ]

    operations = [
        migrations.AlterField(
            model_name='docket',
            name='nature_of_suit',
            field=models.CharField(help_text=b'The nature of suit code from PACER.', max_length=1000, blank=True),
        ),
    ]
