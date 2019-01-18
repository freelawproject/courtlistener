# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models

from cl.lib.db_tools import queryset_generator
from cl.lib.model_helpers import make_docket_number_core


def populate_docket_number_core_field(apps, schema_editor):
    Docket = apps.get_model('search', 'Docket')
    ds = Docket.objects.filter(
        court__jurisdiction='FD',
        docket_number_core='',
    ).only('docket_number')

    for d in queryset_generator(ds):
        d.docket_number_core = make_docket_number_core(d.docket_number)
        d.save()


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0082_idb_updates'),
    ]

    operations = [
        migrations.RunPython(populate_docket_number_core_field),
    ]
