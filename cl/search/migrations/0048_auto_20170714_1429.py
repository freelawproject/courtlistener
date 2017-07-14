# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import cl.lib.fields


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0047_auto_20170424_1210'),
    ]

    operations = [
        migrations.AlterField(
            model_name='docket',
            name='docket_number',
            field=cl.lib.fields.CharNullField(help_text=b'The docket numbers of a case, can be consolidated and quite long', max_length=5000, null=True, db_index=True, blank=True),
        ),
        migrations.AlterField(
            model_name='docket',
            name='pacer_case_id',
            field=cl.lib.fields.CharNullField(help_text=b'The cased ID provided by PACER.', max_length=100, null=True, db_index=True, blank=True),
        ),
    ]
