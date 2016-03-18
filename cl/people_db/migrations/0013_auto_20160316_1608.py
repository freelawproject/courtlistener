# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('people_db', '0012_auto_20160316_1446'),
    ]

    operations = [
        migrations.AlterField(
            model_name='person',
            name='gender',
            field=models.CharField(blank=True, max_length=2, choices=[(b'm', b'Male'), (b'f', b'Female'), (b'o', b'Other')]),
        ),
    ]
