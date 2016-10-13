# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('alerts', '0004_auto_20150910_1450'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='alert',
            name='always_send_email',
        ),
    ]
