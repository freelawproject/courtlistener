# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0060_add_index_date_field_to_dockets'),
    ]

    operations = [
        migrations.AddField(
            model_name='recapdocument',
            name='ia_upload_failure_count',
            field=models.SmallIntegerField(help_text=b'Number of times the upload to the Internet Archive failed.', null=True, blank=True),
        ),
    ]
