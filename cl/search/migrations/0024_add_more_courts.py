# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations

from cl.lib.migration_utils import load_migration_fixture

fixtures = ['court_data_new', 'court_data_new2']


def load_fixtures(apps, schema_editor):
    # This reloads the court_data_new.json fixture, because it had typos and
    # other bad values. It then loads the latest fixtures as well.
    for fixture in fixtures:
        load_migration_fixture(apps, schema_editor, fixture, 'search')


def unload_fixture(apps, schema_editor):
    Court = apps.get_model("search", "Court")
    new_pks = ['kingsbench', 'texjpml', 'njch', 'tennsuperct']
    for pk in new_pks:
        Court.objects.get(pk=pk).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0023_add_i18n_jurisdictions'),
    ]

    operations = [
        migrations.RunPython(load_fixtures, reverse_code=unload_fixture),
    ]
