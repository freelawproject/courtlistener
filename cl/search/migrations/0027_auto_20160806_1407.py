# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0026_auto_20160629_1355'),
    ]

    operations = [
        migrations.AlterField(
            model_name='opinioncluster',
            name='federal_cite_one',
            field=models.CharField(help_text=b'Primary federal citation', max_length=50, db_index=True, blank=True),
        ),
        migrations.AlterField(
            model_name='opinioncluster',
            name='federal_cite_three',
            field=models.CharField(help_text=b'Tertiary federal citation', max_length=50, db_index=True, blank=True),
        ),
        migrations.AlterField(
            model_name='opinioncluster',
            name='federal_cite_two',
            field=models.CharField(help_text=b'Secondary federal citation', max_length=50, db_index=True, blank=True),
        ),
    ]
