# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0071_set_recap_ia_fields_to_true'),
    ]

    operations = [
        migrations.AlterIndexTogether(
            name='docket',
            index_together=set([('ia_upload_failure_count', 'ia_needs_upload', 'ia_date_first_change')]),
        ),
    ]
