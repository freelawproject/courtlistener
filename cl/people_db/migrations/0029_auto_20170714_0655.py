# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('people_db', '0028_auto_20170425_1120'),
    ]

    operations = [
        migrations.AlterField(
            model_name='position',
            name='how_selected',
            field=models.CharField(blank=True, help_text=b'The method that was used for selecting this judge for this position (generally an election or appointment).', max_length=20, choices=[(b'Election', ((b'e_part', b'Partisan Election'), (b'e_non_part', b'Non-Partisan Election'))), (b'Appointment', ((b'a_pres', b'Appointment (President)'), (b'a_gov', b'Appointment (Governor)'), (b'a_legis', b'Appointment (Legislature)'), (b'a_judge', b'Appointment (Judge)')))]),
        ),
    ]
