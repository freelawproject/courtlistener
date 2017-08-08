# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations

from cl.lib.migration_utils import load_migration_fixture

fixture = 'psc_court'


def load_fixture(apps, schema_editor):
    load_migration_fixture(apps, schema_editor, fixture, 'search')


def unload_fixture(apps, schema_editor):
    """Delete everything"""
    Court = apps.get_model("search", "Court")
    Court.objects.get(pk='psc').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0007_make_court_position_non_nullable_issue_481'),
    ]

    operations = [
        migrations.RunPython(load_fixture, reverse_code=unload_fixture),
    ]
