# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('people_db', '0029_auto_20170714_0655'),
    ]

    operations = [
        migrations.AlterField(
            model_name='position',
            name='termination_reason',
            field=models.CharField(blank=True, help_text=b'The reason for a termination', max_length=25, choices=[(b'ded', b'Death'), (b'retire_vol', b'Voluntary Retirement'), (b'retire_mand', b'Mandatory Retirement'), (b'resign', b'Resigned'), (b'other_pos', b'Appointed to Other Judgeship'), (b'lost', b'Lost Election'), (b'abolished', b'Court Abolished'), (b'bad_judge', b'Impeached and Convicted'), (b'recess_not_confirmed', b'Recess Appointment Not Confirmed'), (b'termed_out', b'Term Limit Reached')]),
        ),
    ]
