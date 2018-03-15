# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('people_db', '0031_add_financial_disclosures'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='attorney',
            unique_together=set([]),
        ),
    ]
