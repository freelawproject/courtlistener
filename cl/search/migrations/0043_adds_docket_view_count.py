# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0042_make_pacer_doc_id_nullable'),
    ]

    operations = [
        migrations.AddField(
            model_name='docket',
            name='view_count',
            field=models.IntegerField(default=0, help_text=b'The number of times the docket has been seen.'),
        ),
    ]
