# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0012_auto_20160223_1621'),
    ]

    operations = [
        migrations.AddField(
            model_name='docket',
            name='date_cert_denied',
            field=models.DateField(help_text=b'the date cert was denied for this case, if applicable', null=True, db_index=True, blank=True),
        ),
        migrations.AddField(
            model_name='docket',
            name='date_cert_granted',
            field=models.DateField(help_text=b'date cert was granted for this case, if applicable', null=True, db_index=True, blank=True),
        ),
    ]
