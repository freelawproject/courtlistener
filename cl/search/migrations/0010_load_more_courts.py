# -*- coding: utf-8 -*-


import sys

from django.db import migrations, models

from cl.lib.migration_utils import load_migration_fixture


def load_fixture(apps, schema_editor):
    if 'test' in sys.argv:
        return None
    else:
        fixture = 'harvard_court_data'
    load_migration_fixture(apps, schema_editor, fixture, 'search')


def unload_fixture(apps, schema_editor):
    return None

class Migration(migrations.Migration):

    dependencies = [
        ('search', '0009_alter_court_jurisdiction'),
    ]

    operations = [
        migrations.RunPython(load_fixture, reverse_code=unload_fixture),
    ]
