# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations

from cl.lib.migration_utils import load_migration_fixture

fixture = 'initial_recap_scrape'


def load_fixture(apps, schema_editor):
    load_migration_fixture(apps, schema_editor, fixture, 'scrapers')


def unload_fixture(apps, schema_editor):
    """Delete everything"""
    RECAPLog = apps.get_model("scrapers", "RECAPLog")
    RECAPLog.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('scrapers', '0002_initial_recap_scraper'),
    ]

    operations = [
        migrations.RunPython(load_fixture, reverse_code=unload_fixture)
    ]
