# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0057_auto_20170919_1246'),
    ]

    operations = [
        migrations.AlterField(
            model_name='docket',
            name='date_last_filing',
            field=models.DateField(help_text=b"The date the case was last updated in the docket, as shown in PACER's Docket History report.", null=True, blank=True),
        ),
    ]
