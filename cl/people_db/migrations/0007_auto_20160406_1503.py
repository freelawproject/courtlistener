# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('people_db', '0006_person_cl_id'),
    ]

    operations = [
        migrations.AlterField(
            model_name='person',
            name='cl_id',
            field=models.CharField(help_text=b'A unique identifier for judge, also indicating source of data.', unique=True, max_length=30, db_index=True),
        ),
        migrations.AlterField(
            model_name='person',
            name='is_alias_of',
            field=models.ForeignKey(related_name='aliases', blank=True, to='people_db.Person', null=True),
        ),
    ]
