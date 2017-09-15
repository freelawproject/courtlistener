# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0054_auto_20170912_1706'),
    ]

    operations = [
        migrations.AddField(
            model_name='court',
            name='fjc_court_id',
            field=models.CharField(help_text=b'The ID used by FJC in the Integrated Database', max_length=3, blank=True),
        ),
    ]
