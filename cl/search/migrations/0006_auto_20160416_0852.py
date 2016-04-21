# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0005_allow_blank_fks_in_docket'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='opinioncluster',
            name='per_curiam',
        ),
        migrations.AddField(
            model_name='opinion',
            name='per_curiam',
            field=models.BooleanField(default=False, help_text=b'Is this opinion per curiam, without a single author?'),
        ),
    ]
