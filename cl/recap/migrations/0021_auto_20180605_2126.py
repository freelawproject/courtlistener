# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('recap', '0020_make_fjc_db_indexes'),
    ]

    operations = [
        migrations.AlterField(
            model_name='fjcintegrateddatabase',
            name='defendant',
            field=models.TextField(help_text=b'First listed defendant. This field appears to be cut off at 30 characters.', db_index=True, blank=True),
        ),
        migrations.AlterField(
            model_name='fjcintegrateddatabase',
            name='plaintiff',
            field=models.TextField(help_text=b'First listed plaintiff. This field appears to be cut off at 30 characters', db_index=True, blank=True),
        ),
    ]
