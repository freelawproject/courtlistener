# -*- coding: utf-8 -*-


from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0027_auto_20160806_1407'),
    ]

    operations = [
        migrations.AddField(
            model_name='recapdocument',
            name='ocr_status',
            field=models.SmallIntegerField(blank=True, help_text='The status of OCR processing on this item.', null=True, choices=[(1, 'OCR Complete'), (2, 'OCR Not Necessary')]),
        ),
        migrations.AddField(
            model_name='recapdocument',
            name='plain_text',
            field=models.TextField(help_text='Plain text of the document after extraction using pdftotext, wpd2txt, etc.', blank=True),
        ),
    ]
