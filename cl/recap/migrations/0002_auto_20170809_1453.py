# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('recap', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='processingqueue',
            name='attachment_number',
            field=models.SmallIntegerField(help_text=b'If the file is an attachment, the number is the attachment number on the docket.', null=True, blank=True),
        ),
        migrations.AlterField(
            model_name='processingqueue',
            name='document_number',
            field=models.CharField(help_text=b'The docket entry number for the document.', max_length=32, blank=True),
        ),
        migrations.AlterField(
            model_name='processingqueue',
            name='pacer_doc_id',
            field=models.CharField(help_text=b'The ID of the document in PACER.', unique=True, max_length=32, blank=True),
        ),
        migrations.AlterField(
            model_name='processingqueue',
            name='status',
            field=models.SmallIntegerField(default=1, help_text=b'The current status of this upload. Possible values are: (1): Awaiting processing in queue., (2): Item processed successfully., (3): Item encountered an error while processing., (4): Item is currently being processed., (5): Item failed processing, but will be retried.', choices=[(1, b'Awaiting processing in queue.'), (2, b'Item processed successfully.'), (3, b'Item encountered an error while processing.'), (4, b'Item is currently being processed.'), (5, b'Item failed processing, but will be retried.')]),
        ),
    ]
