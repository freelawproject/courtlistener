# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


def nullify_fields(apps, schema_editor):
    """Set any docket_number of pacer_case_id number that's '' to Null"""
    Docket = apps.get_model('search', 'Docket')
    Docket.objects.filter(pacer_case_id='').update(pacer_case_id=None)
    Docket.objects.filter(docket_number='').update(docket_number=None)


def blankify_fields(apps, schema_editor):
    """Set any null value in docket_number or pacer_case_id back to blank"""
    Docket = apps.get_model('search', 'Docket')
    Docket.objects.filter(pacer_case_id=None).update(pacer_case_id='')
    Docket.objects.filter(docket_number=None).update(docket_number='')


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0048_auto_20170714_1429'),
    ]

    operations = [
        migrations.RunPython(nullify_fields, blankify_fields),
    ]
