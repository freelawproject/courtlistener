# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('scrapers', '0008_add_pacer_report_row'),
    ]

    operations = [
        migrations.AddField(
            model_name='pacerfreedocumentrow',
            name='error_msg',
            field=models.TextField(default=''),
            preserve_default=False,
        ),
    ]
