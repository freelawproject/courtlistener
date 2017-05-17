# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import sys
from django.core.management import call_command
from django.db import models, migrations


def load_fixture(apps, schema_editor):
    if 'test' in sys.argv:
        fixture = 'court_data_truncated'
    else:
        fixture = 'court_data'
    call_command('loaddata', fixture, app_label='search')


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
