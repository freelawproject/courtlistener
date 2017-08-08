# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models

from cl.lib.migration_utils import load_migration_fixture


def load_fixture(apps, schema_editor):
    load_migration_fixture(apps, schema_editor, 'races', 'people_db')


def unload_fixture(apps, schema_editor):
    RaceModel = apps.get_model('people_db', 'Race')
    RaceModel.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('people_db', '0003_load_initial_data'),
    ]

    operations = [
        migrations.RunPython(load_fixture, reverse_code=unload_fixture),
    ]
