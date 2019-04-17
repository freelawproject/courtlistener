# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('people_db', '0037_add_criminal_data_fields'),
    ]

    operations = [
        migrations.AlterField(
            model_name='criminalcomplaint',
            name='disposition',
            field=models.TextField(help_text=b'The disposition of the criminal complaint.', blank=True),
        ),
        migrations.AlterField(
            model_name='partytype',
            name='extra_info',
            field=models.TextField(help_text=b'Additional info from PACER', db_index=True, blank=True),
        ),
    ]
