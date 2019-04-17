# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('alerts', '0005_remove_alert_always_send_email'),
    ]

    operations = [
        migrations.AddField(
            model_name='alert',
            name='secret_key',
            field=models.CharField(default='', max_length=40, verbose_name=b'A key to be used in links to access the alert without having to log in. Can be used for a variety of purposes.'),
            preserve_default=False,
        ),
    ]
