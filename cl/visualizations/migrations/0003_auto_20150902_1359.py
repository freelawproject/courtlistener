# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('visualizations', '0002_auto_20150902_1310'),
    ]

    operations = [
        migrations.CreateModel(
            name='JSONVersion',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('date_created', models.DateTimeField(help_text=b'The time when this item was created', auto_now_add=True, db_index=True)),
                ('date_modified', models.DateTimeField(help_text=b'The last moment when the item was modified.', auto_now=True, db_index=True)),
                ('json_data', models.TextField(help_text=b'The JSON data for a particular version of the visualization.')),
                ('map', models.ForeignKey(related_name='json_versions', to='visualizations.SCOTUSMap', help_text=b'The visualization that the json is affiliated with.')),
            ],
        ),
        migrations.RemoveField(
            model_name='jsonversions',
            name='map',
        ),
        migrations.DeleteModel(
            name='JSONVersions',
        ),
    ]
