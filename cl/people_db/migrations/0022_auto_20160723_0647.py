# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('people_db', '0021_person_ftm_total_received'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='person',
            name='ftm_id',
        ),
        migrations.AddField(
            model_name='person',
            name='ftm_eid',
            field=models.CharField(help_text=b'The ID of a judge as assigned by the Follow the Money database.', max_length=30, null=True, blank=True),
        ),
    ]
