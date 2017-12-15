# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0058_auto_20171012_1437'),
    ]

    operations = [
        migrations.AlterField(
            model_name='recapdocument',
            name='pacer_doc_id',
            field=models.CharField(default='', help_text=b'The ID of the document in PACER. This information is provided by RECAP.', max_length=32, blank=True),
            preserve_default=False,
        ),
    ]
