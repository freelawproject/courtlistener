# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('people_db', '0027_add_date_action_to_unique_fields'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='attorney',
            options={'permissions': (('has_recap_api_access', 'Can work with RECAP API'),)},
        ),
        migrations.AlterModelOptions(
            name='party',
            options={'verbose_name_plural': 'Parties', 'permissions': (('has_recap_api_access', 'Can work with RECAP API'),)},
        ),
    ]
