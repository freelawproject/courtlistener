# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0001_initial'),
        ('favorites', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='favorite',
            name='cluster_id',
            field=models.ForeignKey(verbose_name=b'the opinion cluster that is favorited', blank=True, to='search.OpinionCluster', null=True),
        ),
    ]
