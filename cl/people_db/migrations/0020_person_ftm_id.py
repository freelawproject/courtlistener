# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('people_db', '0019_update_help_text_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='person',
            name='ftm_id',
            field=models.CharField(help_text=b'The ID of a judge as assigned by the Follow the Money database.', max_length=30, unique=True, null=True, blank=True),
        ),
    ]
