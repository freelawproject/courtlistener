# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import sys
from django.core.management import call_command
from django.db import models, migrations


def load_fixture(apps, schema_editor):
    # Every time tests are run, the migrations are applied, importing this data.
    # Because the standard school data has more than 6,000 items, it takes too
    # long to import, and instead we import a miniature version.
    #if 'test' in sys.argv:
        # Testing mode.
    #    fixture = 'school_data_truncated'
    #else:
    #    fixture = 'schools_data'
    call_command('loaddata', 'schools_data', app_label='people_db')


def unload_fixture(apps, schema_editor):
    """Delete everything"""
    SchoolModel = apps.get_model("people_db", "School")
    SchoolModel.objects.all().delete()

class Migration(migrations.Migration):
    dependencies = [
        ('people_db', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(load_fixture, reverse_code=unload_fixture),
    ]

