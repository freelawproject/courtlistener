# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0003_auto_20150826_0632'),
    ]

    operations = [
        migrations.RenameField(
            model_name='opinioncluster',
            old_name='supreme_court_db_id',
            new_name='scdb_id',
        ),
    ]
