# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0050_auto_20170714_1440'),
    ]

    operations = [
        migrations.AddField(
            model_name='court',
            name='pacer_court_id',
            field=models.PositiveSmallIntegerField(help_text=b'The numeric ID for the court in PACER. This can be found by looking at the first three digits of any doc1 URL in PACER.', null=True, blank=True),
        ),
    ]
