# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('people_db', '0009_merge'),
    ]

    operations = [
        migrations.AlterField(
            model_name='position',
            name='how_selected',
            field=models.CharField(blank=True, max_length=20, choices=[(b'Election', ((b'e_part', b'Partisan Election'), (b'e_non_part', b'Non-Partisan Election'))), (b'Appointment', ((b'a_pres', b'Appointment (President)'), (b'a_gov', b'Appointment (Governor)'), (b'a_legis', b'Appointment (Legislature)')))]),
        ),
    ]
