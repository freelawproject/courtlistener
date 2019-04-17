# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0075_add_citation_table'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='opinioncluster',
            name='citation_id',
        ),
    ]
