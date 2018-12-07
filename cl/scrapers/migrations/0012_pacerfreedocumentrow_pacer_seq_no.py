# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('scrapers', '0011_delete_recaplog'),
    ]

    operations = [
        migrations.AddField(
            model_name='pacerfreedocumentrow',
            name='pacer_seq_no',
            field=models.IntegerField(null=True, blank=True),
        ),
    ]
