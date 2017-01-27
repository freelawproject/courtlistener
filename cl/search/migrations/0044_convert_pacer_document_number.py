# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0043_adds_docket_view_count'),
    ]

    operations = [
        migrations.AlterField(
            model_name='recapdocument',
            name='document_number',
            field=models.CharField(help_text=b'If the file is a document, the number is the document_number in RECAP docket.', max_length=32, db_index=True),
        ),
    ]
