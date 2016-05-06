# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0009_nuke_nulls_on_char_fields'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='docket',
            unique_together=set([]),
        ),
    ]
