# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0005_add_user_notes_field'),
    ]

    operations = [
        migrations.AddField(
            model_name='userprofile',
            name='unlimited_docket_alerts',
            field=models.BooleanField(default=False, help_text=b'Should the user get unlimited docket alerts?'),
        ),
    ]
