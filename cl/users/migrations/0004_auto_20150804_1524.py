# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0003_remove_userprofile_alert'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='userprofile',
            name='donation',
        ),
        migrations.RemoveField(
            model_name='userprofile',
            name='favorite',
        ),
    ]
