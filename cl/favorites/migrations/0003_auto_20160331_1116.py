# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('favorites', '0002_auto_20160318_1735'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='favorite',
            unique_together=set([('cluster_id', 'user'), ('audio_id', 'user')]),
        ),
    ]
