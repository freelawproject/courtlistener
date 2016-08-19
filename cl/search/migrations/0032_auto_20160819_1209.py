# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0031_convert_to_bigint_recap_document'),
    ]

    operations = [
        migrations.AlterField(
            model_name='docket',
            name='nature_of_suit',
            field=models.CharField(help_text=b'The nature of suit code from PACER.', max_length=500, blank=True),
        ),
    ]
