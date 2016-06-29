# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.core.management import call_command
from django.db import migrations

fixtures = ['court_data_new3']


def load_fixtures(apps, schema_editor):
    for fixture in fixtures:
        call_command('loaddata', fixture, app_label='search')


def unload_fixture(apps, schema_editor):
    Court = apps.get_model("search", "Court")
    new_pks = ['circtdel']
    for pk in new_pks:
        Court.objects.get(pk=pk).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0024_add_more_courts'),
    ]

    operations = [
        migrations.RunPython(load_fixtures, reverse_code=unload_fixture),
    ]
