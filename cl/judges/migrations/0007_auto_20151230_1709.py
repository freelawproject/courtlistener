# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('judges', '0006_auto_20151221_1551'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='judge',
            options={'permissions': (('has_beta_api_access', 'Can access features during beta period.'),)},
        ),
    ]
