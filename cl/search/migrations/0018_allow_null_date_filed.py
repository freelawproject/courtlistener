# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0017_make_docket_paths_optional'),
    ]

    operations = [
        migrations.AlterField(
            model_name='docketentry',
            name='date_filed',
            field=models.DateField(help_text=b'The created date of the Docket Entry.', null=True, blank=True),
        ),
    ]
