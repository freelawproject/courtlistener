# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0018_allow_null_date_filed'),
    ]

    operations = [
        migrations.AddField(
            model_name='docket',
            name='assigned_to_str',
            field=models.TextField(help_text=b'The judge that the case was assigned to, as a string.', blank=True),
        ),
        migrations.AddField(
            model_name='docket',
            name='referred_to_str',
            field=models.TextField(help_text=b'The judge that the case was referred to, as a string.', blank=True),
        ),
    ]
