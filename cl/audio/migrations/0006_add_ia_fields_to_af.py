# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('audio', '0005_auto_20161103_1436'),
    ]

    operations = [
        migrations.AddField(
            model_name='audio',
            name='filepath_ia',
            field=models.CharField(help_text=b'The URL of the file in IA', max_length=1000, blank=True),
        ),
        migrations.AddField(
            model_name='audio',
            name='ia_upload_failure_count',
            field=models.SmallIntegerField(help_text=b'Number of times the upload to the Internet Archive failed.', null=True, blank=True),
        ),
    ]
