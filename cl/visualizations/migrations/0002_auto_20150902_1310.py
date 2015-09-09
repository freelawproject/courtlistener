# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('visualizations', '0001_initial'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='scotusmap',
            name='degree_count',
        ),
        migrations.AlterField(
            model_name='scotusmap',
            name='clusters',
            field=models.ManyToManyField(help_text=b'The clusters involved in this visualization, including the start and end clusters.', related_name='visualizations', to='search.OpinionCluster', blank=True),
        ),
    ]
