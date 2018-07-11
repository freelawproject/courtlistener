# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0067_add_file_size'),
    ]

    operations = [
        migrations.AddField(
            model_name='docket',
            name='mdl_status',
            field=models.CharField(help_text=b'The MDL status of a case before the Judicial Panel for Multidistrict Litigation', max_length=100, blank=True),
        ),
    ]
