# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations

from cl.search.models import Docket as NewDocket


def set_recap_ia_fields_true(apps, schema_editor):
    """When we initially do this, we want all of the RECAP dockets to be set
    to needing IA upload.
    """
    Docket = apps.get_model('search', 'Docket')
    Docket.objects.filter(
        # Use NewDocket here b/c the model imported by get_model doesn't have
        # the RECAP_SOURCES attribute.
        source__in=NewDocket.RECAP_SOURCES,
    ).update(
        ia_needs_upload=True
    )


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0070_add_recap_ia_columns'),
    ]

    operations = [
        migrations.RunPython(set_recap_ia_fields_true),
    ]
