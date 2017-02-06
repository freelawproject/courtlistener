# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import datetime


class Migration(migrations.Migration):

    dependencies = [
        ('people_db', '0026_make_lookup_key_unique'),
    ]

    operations = [
        migrations.AddField(
            model_name='attorney',
            name='date_sourced',
            field=models.DateField(default=datetime.date(1750, 1, 1), help_text=b'The latest date on the source docket that populated this information. When information is in conflict use the latest data.', db_index=True),
            preserve_default=False,
        ),
    ]
