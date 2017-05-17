# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import sys
from django.core.management import call_command
from django.db import migrations, models


def load_fixture(apps, schema_editor):
    if 'test' in sys.argv:
        fixture = 'pacer_free_docs_initial_data_truncated'
    else:
        fixture = 'pacer_free_docs_initial_data'
    call_command('loaddata', fixture, app_label='scrapers')


def unload_fixture(apps, schema_editor):
    """Delete everything"""
    PACERFreeDocumentLog = apps.get_model("scrapers", "PACERFreeDocumentLog")
    PACERFreeDocumentLog.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('scrapers', '0006_add_free_opinions_report'),
    ]

    operations = [
        migrations.RunPython(load_fixture, reverse_code=unload_fixture)
    ]
