# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Stat',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('name', models.CharField(max_length=50, db_index=True)),
                ('date_logged', models.DateField(db_index=True)),
                ('count', models.IntegerField()),
            ],
        ),
        migrations.AlterUniqueTogether(
            name='stat',
            unique_together=set([('date_logged', 'name')]),
        ),
    ]
