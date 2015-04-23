# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from django.core.management import call_command
from django.db import models, migrations

fixture = 'school_data'


def load_fixture(apps, schema_editor):
    call_command('loaddata', fixture, app_label='judges')


def unload_fixture(apps, schema_editor):
    """Delete everything"""
    SchoolModel = apps.get_model("judges", "School")
    SchoolModel.objects.all().delete()

class Migration(migrations.Migration):
    dependencies = [
        ('judges', '0003_auto_20150713_1218'),
    ]

    operations = [
        migrations.RunPython(load_fixture, reverse_code=unload_fixture),
    ]

