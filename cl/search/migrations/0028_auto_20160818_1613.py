# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0027_auto_20160806_1407'),
    ]

    operations = [
        migrations.AddField(
            model_name='recapdocument',
            name='ocr_status',
            field=models.SmallIntegerField(blank=True, help_text=b'The status of OCR processing on this item.', null=True, choices=[(1, b'OCR Complete'), (2, b'OCR Not Necessary')]),
        ),
        migrations.AddField(
            model_name='recapdocument',
            name='plain_text',
            field=models.TextField(help_text=b'Plain text of the document after extraction using pdftotext, wpd2txt, etc.', blank=True),
        ),
    ]
