# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import sys
from django.db import models, migrations

from cl.lib.migration_utils import load_migration_fixture


def load_fixture(apps, schema_editor):
    if 'test' in sys.argv:
        fixture = 'bar_membership_data_truncated'
    else:
        fixture = 'bar_membership_data'
    load_migration_fixture(apps, schema_editor, fixture, 'users')


def unload_fixture(apps, schema_editor):
    """Delete everything"""
    BarMembershipModel = apps.get_model("users", "BarMembership")
    BarMembershipModel.objects.all().delete()

class Migration(migrations.Migration):

    dependencies = [
        ('users', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(load_fixture, reverse_code=unload_fixture),
    ]

