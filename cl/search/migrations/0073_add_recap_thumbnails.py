# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models

import cl.lib.model_helpers
import cl.lib.storage


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0072_add_multicolumn_ia_index'),
    ]

    operations = [
        migrations.AddField(
            model_name='recapdocument',
            name='thumbnail',
            field=models.FileField(help_text=b'A thumbnail of the first page of the document', storage=cl.lib.storage.IncrementingFileSystemStorage(), null=True, upload_to=cl.lib.model_helpers.make_recap_path, blank=True),
        ),
        migrations.AddField(
            model_name='recapdocument',
            name='thumbnail_status',
            field=models.SmallIntegerField(default=0, help_text=b'The status of the thumbnail generation', choices=[(0, b'Thumbnail needed'), (1, b'Thumbnail completed successfully'), (2, b'Unable to generate thumbnail')]),
        ),
    ]
