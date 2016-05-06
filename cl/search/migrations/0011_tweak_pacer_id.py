# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0010_auto_20160506_1544'),
    ]

    operations = [
        migrations.AlterField(
            model_name='docket',
            name='pacer_case_id',
            field=models.CharField(help_text=b'The cased ID provided by PACER.', max_length=100, null=True, db_index=True, blank=True),
        ),
    ]
