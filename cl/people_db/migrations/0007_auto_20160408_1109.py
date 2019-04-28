# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('people_db', '0006_person_cl_id'),
    ]

    operations = [
        migrations.RenameField(
            model_name='education',
            old_name='degree',
            new_name='degree_detail',
        ),
        migrations.AlterField(
            model_name='person',
            name='is_alias_of',
            field=models.ForeignKey(related_name='aliases', blank=True, to='people_db.Person', null=True,
                                    on_delete=models.CASCADE),
        ),
        migrations.AlterField(
            model_name='position',
            name='date_retirement',
            field=models.DateField(help_text=b'The date when they become a senior judge by going into active retirement', null=True, db_index=True, blank=True),
        ),
        migrations.AlterField(
            model_name='position',
            name='date_termination',
            field=models.DateField(help_text=b'The last date of their employment. The compliment to date_start', null=True, db_index=True, blank=True),
        ),
        migrations.AlterField(
            model_name='position',
            name='organization_name',
            field=models.CharField(help_text=b"If org isn't court or school, type here.", max_length=120, null=True, blank=True),
        ),
    ]
