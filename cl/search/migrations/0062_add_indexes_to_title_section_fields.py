# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0061_add_ia_upload_failure_count'),
    ]

    operations = [
        migrations.AlterField(
            model_name='opinioncluster',
            name='lexis_cite',
            field=models.CharField(help_text=b'LexisNexis citation (e.g. 1 LEXIS 38237)', max_length=50, blank=True),
        ),
    ]
