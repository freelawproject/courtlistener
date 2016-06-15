# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models

import cl.lib.model_helpers
import cl.lib.storage


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0016_auto_20160608_1035'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='recapdocument',
            options={'ordering': ('document_number', 'attachment_number')},
        ),
        migrations.AlterField(
            model_name='recapdocument',
            name='filepath_ia',
            field=models.CharField(help_text=b'The URL of the file in IA', max_length=1000, blank=True),
        ),
        migrations.AlterField(
            model_name='recapdocument',
            name='filepath_local',
            field=models.FileField(help_text=b'The path of the file in the local storage area.', storage=cl.lib.storage.IncrementingFileSystemStorage(), max_length=1000, upload_to=cl.lib.model_helpers.make_recap_path, blank=True),
        ),
    ]
