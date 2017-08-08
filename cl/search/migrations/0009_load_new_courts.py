# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations
from django.db.migrations import RunPython

from cl.lib.migration_utils import load_migration_fixture

fixture = 'court_data_new'


def load_fixture(apps, schema_editor):
    load_migration_fixture(apps, schema_editor, fixture, 'search')


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0008_auto_20160518_1131'),
    ]

    operations = [
        migrations.RunPython(load_fixture, reverse_code=RunPython.noop),
    ]
