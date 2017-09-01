# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('recap', '0003_auto_20170809_1543'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='processingqueue',
            name='document_number',
        ),
        migrations.AlterField(
            model_name='processingqueue',
            name='pacer_doc_id',
            field=models.CharField(help_text=b'The ID of the document in PACER.', max_length=32, blank=True),
        ),
    ]
