# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0049_auto_20170714_1440'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='docket',
            unique_together=set([('docket_number', 'pacer_case_id', 'court')]),
        ),
    ]
