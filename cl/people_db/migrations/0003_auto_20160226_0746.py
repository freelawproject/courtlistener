# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('people_db', '0001_initial'),
        ('people_db', '0002_load_initial_data'),
    ]

    operations = [
        migrations.AddField(
            model_name='position',
            name='appointer',
            field=models.ForeignKey(related_name='appointed_positions', blank=True, to='people_db.Person', help_text=b'If this is an appointed position, the person responsible for the appointing.', null=True),
        ),
        migrations.AddField(
            model_name='position',
            name='predecessor',
            field=models.ForeignKey(blank=True, to='people_db.Person', null=True),
        ),
        migrations.AddField(
            model_name='position',
            name='supervisor',
            field=models.ForeignKey(related_name='supervised_positions', blank=True, to='people_db.Person', help_text=b'If this is a clerkship, the supervising judge.', null=True),
        ),
    ]
