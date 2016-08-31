# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0036_auto_20160821_1035'),
    ]

    operations = [
        migrations.AddField(
            model_name='opinion',
            name='page_count',
            field=models.IntegerField(help_text=b'The number of pages in the document, if known', null=True, blank=True),
        ),
        migrations.AddField(
            model_name='recapdocument',
            name='page_count',
            field=models.IntegerField(help_text=b'The number of pages in the document, if known', null=True, blank=True),
        ),
    ]
