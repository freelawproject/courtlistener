# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import sys
from django.db import models, migrations

from cl.lib.migration_utils import load_migration_fixture


def load_fixture(apps, schema_editor):
    if 'test' in sys.argv:
        fixture = 'court_data_truncated'
    else:
        fixture = 'court_data'
    load_migration_fixture(apps, schema_editor, fixture, 'search')


def unload_fixture(apps, schema_editor):
    """Delete everything"""
    Court = apps.get_model("search", "Court")
    Court.objects.all().delete()

class Migration(migrations.Migration):

    dependencies = [
        ('search', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(load_fixture, reverse_code=unload_fixture),
    ]
