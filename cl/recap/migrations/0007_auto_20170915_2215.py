# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('recap', '0006_fjcintegrateddatabase'),
    ]

    operations = [
        migrations.AlterField(
            model_name='fjcintegrateddatabase',
            name='docket_number',
            field=models.CharField(default='', help_text=b"The number assigned by the Clerks' office; consists of 2 digit Docket Year (usually calendar year in which the case was filed) and 5 digit sequence number.", max_length=7, blank=True),
            preserve_default=False,
        ),
    ]
