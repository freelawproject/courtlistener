# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('favorites', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='favorite',
            name='cluster_id',
            field=models.ForeignKey(verbose_name=b'the opinion cluster that is favorited', blank=True, to='search.OpinionCluster', null=True),
        ),
        migrations.AddField(
            model_name='favorite',
            name='user',
            field=models.ForeignKey(related_name='favorites', to=settings.AUTH_USER_MODEL, help_text=b'The user that owns the favorite'),
        ),
    ]
