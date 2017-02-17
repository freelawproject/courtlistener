# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('people_db', '0026_update_role_uniq_together_constraint'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='role',
            unique_together=set([('party', 'attorney', 'role', 'docket', 'date_action')]),
        ),
    ]
