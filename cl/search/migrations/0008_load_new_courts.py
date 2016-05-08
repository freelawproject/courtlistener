# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.core.management import call_command
from django.db import migrations

fixture = 'psc_court'


def load_fixture(apps, schema_editor):
    call_command('loaddata', fixture, app_label='search')


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
