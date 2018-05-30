# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('recap', '0019_add_ia_docket_type'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='fjcintegrateddatabase',
            options={'verbose_name_plural': 'FJC Integrated Database Entries'},
        ),
        migrations.AlterField(
            model_name='fjcintegrateddatabase',
            name='defendant',
            field=models.TextField(help_text=b'First listed defendant', db_index=True, blank=True),
        ),
        migrations.AlterField(
            model_name='fjcintegrateddatabase',
            name='plaintiff',
            field=models.TextField(help_text=b'First listed plaintiff', db_index=True, blank=True),
        ),
    ]
