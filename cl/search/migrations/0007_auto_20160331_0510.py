# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0006_auto_20160331_0458'),
    ]

    operations = [
        migrations.AddField(
            model_name='recapdocument',
            name='fdsys_document_number',
            field=models.PositiveIntegerField(help_text=b'document_number in FDSYS docket.', null=True, blank=True),
        ),
        migrations.AlterField(
            model_name='recapdocument',
            name='document_number',
            field=models.PositiveIntegerField(help_text=b'If the file is a document, the number is the document_number in RECAP docket.', null=True, blank=True),
        ),
        migrations.AlterUniqueTogether(
            name='recapdocument',
            unique_together=set([('docket_entry', 'document_number', 'attachment_number', 'fdsys_document_number')]),
        ),
    ]
