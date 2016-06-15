# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.core.management import call_command
from django.db import migrations
from django.db.migrations import RunPython

fixture = 'court_data_new'


def load_fixture(apps, schema_editor):
    call_command('loaddata', fixture, app_label='search')


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0008_auto_20160518_1131'),
    ]

    operations = [
        migrations.RunPython(load_fixture, reverse_code=RunPython.noop),
    ]
