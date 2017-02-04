# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('people_db', '0024_auto_20170202_2253'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='party',
            options={'verbose_name_plural': 'Parties'},
        ),
        migrations.AddField(
            model_name='attorneyorganization',
            name='lookup_key',
            field=models.TextField(default='', help_text=b'A trimmed version of the address for duplicate matching.', db_index=True),
            preserve_default=False,
        ),
    ]
