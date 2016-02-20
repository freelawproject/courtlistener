# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('visualizations', '0006_remove_scotusmap_subtitle'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='scotusmap',
            options={'permissions': (('has_beta_access', 'Can access features during beta period.'),)},
        ),
    ]
