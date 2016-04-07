# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0008_auto_20160331_0512'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='docket',
            name='sha1',
        ),
    ]
