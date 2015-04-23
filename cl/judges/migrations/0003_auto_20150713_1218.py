# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):
    dependencies = [
        ('judges', '0002_auto_20150708_1801'),
    ]

    operations = [
        migrations.AlterField(
            model_name='school',
            name='unit_id',
            field=models.IntegerField(help_text=b'This is the ID assigned by the Department of Education, as found in the data on their API.', unique=True, null=True, db_index=True),
        ),
        migrations.AlterField(
            model_name='school',
            name='ein',
            field=models.IntegerField(help_text=b'The EIN assigned by the IRS', null=True, db_index=True, blank=True),
        ),
        migrations.AlterField(
            model_name='school',
            name='ope_id',
            field=models.IntegerField(
                help_text=b"This is the ID assigned by the Department of Education's Office of Postsecondary Education (OPE) for schools that have a Program Participation Agreement making them eligible for aid from the Federal Student Financial Assistance Program",
                null=True, db_index=True, blank=True),
        ),
    ]
