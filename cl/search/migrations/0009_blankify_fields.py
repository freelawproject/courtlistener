# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations


def blankify_fields(apps, schema_editor):
    """Set fields to blank if they are equal to null. This is needed because
    otherwise the next migration tries to change data (setting values to blank)
    and tries to alter the schema (making the fields non-nullable). Because both
    of those things happen in a single transaction, Postgres flips out, and all
    is lost -- much like my time right now.
    """
    fields = ['cause', 'docket_number', 'filepath_ia', 'filepath_local',
              'jurisdiction_type', 'jury_demand', 'nature_of_suit', 'slug']
    Docket = apps.get_model("search", 'Docket')
    for field in fields:
        Docket.objects.filter(**{field: None}).update(**{field: ''})


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0008_load_new_courts'),
    ]


    operations = [
        migrations.RunPython(blankify_fields)
    ]
