# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('recap', '0009_pacerhtmlfiles'),
    ]

    operations = [
        migrations.AddField(
            model_name='processingqueue',
            name='debug',
            field=models.BooleanField(default=False, help_text=b'Are you debugging? Debugging uploads will be validated, but not saved to the database.'),
        ),
    ]
