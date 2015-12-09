# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('visualizations', '0011_auto_20151203_1631'),
    ]

    operations = [
        migrations.AlterField(
            model_name='scotusmap',
            name='notes',
            field=models.TextField(help_text=b'A description to help explain the diagram, in Markdown format', blank=True),
        ),
    ]
