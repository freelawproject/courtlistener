# -*- coding: utf-8 -*-


from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0037_add_page_counts'),
    ]

    operations = [
        migrations.AlterField(
            model_name='recapdocument',
            name='ocr_status',
            field=models.SmallIntegerField(blank=True, help_text='The status of OCR processing on this item.', null=True, choices=[(1, 'OCR Complete'), (2, 'OCR Not Necessary'), (3, 'OCR Failed'), (4, 'OCR Needed')]),
        ),
    ]
