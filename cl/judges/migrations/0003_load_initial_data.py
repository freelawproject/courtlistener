# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from django.core.management import call_command
from django.db import models, migrations


def load_fixture(apps, schema_editor):
    # Every time tests are run, the migrations are applied, importing this data.
    # Because the standard school data has more than 6,000 items, it takes too
    # long to import, and instead we import a miniature version.
    if schema_editor.connection.vendor == u'sqlite':
        # Testing mode.
        fixture = 'school_data_truncated'
    else:
        fixture = 'school_data'
    call_command('loaddata', fixture, app_label='judges')


def unload_fixture(apps, schema_editor):
    """Delete everything"""
    SchoolModel = apps.get_model("judges", "School")
    SchoolModel.objects.all().delete()

class Migration(migrations.Migration):
    dependencies = [
        ('judges', '0002_auto_20150818_0954'),
    ]

    operations = [
        migrations.RunPython(load_fixture, reverse_code=unload_fixture),
    ]

