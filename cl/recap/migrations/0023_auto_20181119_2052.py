# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('recap', '0022_add_failure_count_to_m_donations'),
    ]

    operations = [
        migrations.AlterIndexTogether(
            name='fjcintegrateddatabase',
            index_together=set([('district', 'docket_number')]),
        ),
    ]
