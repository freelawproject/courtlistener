# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('scrapers', '0009_pacerfreedocumentrow_error_msg'),
    ]

    operations = [
        migrations.AlterField(
            model_name='pacerfreedocumentrow',
            name='pacer_doc_id',
            field=models.CharField(max_length=32),
        ),
    ]
