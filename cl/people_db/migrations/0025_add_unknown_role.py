# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('people_db', '0024_add_party_info'),
    ]

    operations = [
        migrations.AlterField(
            model_name='role',
            name='role',
            field=models.SmallIntegerField(help_text=b"The name of the attorney's role.", db_index=True, choices=[(1, b'Attorney to be noticed'), (2, b'Lead attorney'), (3, b'Attorney in sealed group'), (4, b'Pro hac vice'), (5, b'Self-terminated'), (6, b'Terminated'), (7, b'Suspended'), (8, b'Inactive'), (9, b'Disbarred'), (10, b'Unknown')]),
        ),
    ]
