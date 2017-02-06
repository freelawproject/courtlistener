# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('people_db', '0025_add_lookup_key_to_orgs'),
    ]

    operations = [
        migrations.AlterField(
            model_name='attorneyorganization',
            name='lookup_key',
            field=models.TextField(help_text=b'A trimmed version of the address for duplicate matching.', unique=True, db_index=True),
        ),
    ]
