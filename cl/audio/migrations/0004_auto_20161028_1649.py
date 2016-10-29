# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('audio', '0003_auto_20161028_1453'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='audio',
            name='stt_complete',
        ),
        migrations.AddField(
            model_name='audio',
            name='stt_status',
            field=models.SmallIntegerField(default=0, help_text=b'The status of the Speech to Text for this item?', choices=[(0, b'Speech to Text Needed'), (1, b'Speech to Text Complete'), (2, b'Speech to Text Failed')]),
        ),
    ]
