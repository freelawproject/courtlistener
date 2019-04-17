# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models

import cl.lib.model_helpers
import cl.lib.storage


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0073_add_recap_thumbnails'),
    ]

    operations = [
        migrations.AlterField(
            model_name='recapdocument',
            name='filepath_local',
            field=models.FileField(storage=cl.lib.storage.IncrementingFileSystemStorage(), upload_to=cl.lib.model_helpers.make_recap_pdf_path, max_length=1000, blank=True, help_text=b'The path of the file in the local storage area.', db_index=True),
        ),
    ]
