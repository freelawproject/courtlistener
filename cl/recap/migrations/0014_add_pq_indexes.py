# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('recap', '0013_auto_20171122_1338'),
    ]

    operations = [
        migrations.AlterField(
            model_name='processingqueue',
            name='pacer_case_id',
            field=models.CharField(help_text=b'The cased ID provided by PACER.', max_length=100, db_index=True),
        ),
        migrations.AlterField(
            model_name='processingqueue',
            name='pacer_doc_id',
            field=models.CharField(help_text=b'The ID of the document in PACER.', max_length=32, db_index=True, blank=True),
        ),
        migrations.AlterField(
            model_name='processingqueue',
            name='status',
            field=models.SmallIntegerField(default=1, help_text=b'The current status of this upload. Possible values are: (1): Awaiting processing in queue., (2): Item processed successfully., (3): Item encountered an error while processing., (4): Item is currently being processed., (5): Item failed processing, but will be retried., (6): Item failed validity tests.', db_index=True, choices=[(1, b'Awaiting processing in queue.'), (2, b'Item processed successfully.'), (3, b'Item encountered an error while processing.'), (4, b'Item is currently being processed.'), (5, b'Item failed processing, but will be retried.'), (6, b'Item failed validity tests.')]),
        ),
    ]
