# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.core.management import call_command
from django.db import migrations, models


def load_fixture(apps, schema_editor):
    call_command('loaddata', 'races', app_label='people_db')


def unload_fixture(apps, schema_editor):
    RaceModel = apps.get_model('people_db', 'Race')
    RaceModel.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('people_db', '0003_load_initial_data'),
    ]

    operations = [
        migrations.RunPython(load_fixture, reverse_code=unload_fixture),
    ]
