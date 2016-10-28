# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('audio', '0002_auto_20160318_1735'),
    ]

    operations = [
        migrations.AddField(
            model_name='audio',
            name='stt_complete',
            field=models.BooleanField(default=False, help_text=b'Is the Speech to Text complete for this item?'),
        ),
        migrations.AddField(
            model_name='audio',
            name='stt_google_response',
            field=models.TextField(help_text=b'The JSON response object returned by Google Speech.', blank=True),
        ),
    ]
