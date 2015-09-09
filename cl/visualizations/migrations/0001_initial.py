# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0003_auto_20150826_0632'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='JSONVersions',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('date_created', models.DateTimeField(help_text=b'The time when this item was created', auto_now_add=True, db_index=True)),
                ('date_modified', models.DateTimeField(help_text=b'The last moment when the item was modified.', auto_now=True, db_index=True)),
                ('json_data', models.TextField(help_text=b'The JSON data for a particular version of the visualization.')),
            ],
        ),
        migrations.CreateModel(
            name='SCOTUSMap',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('date_created', models.DateTimeField(help_text=b'The time when this item was created', auto_now_add=True, db_index=True)),
                ('date_modified', models.DateTimeField(help_text=b'The last moment when the item was modified.', auto_now=True, db_index=True)),
                ('title', models.CharField(help_text=b"The title of the visualization that you're creating.", max_length=200)),
                ('subtitle', models.CharField(help_text=b"The subtitle of the visualization that you're creating.", max_length=300, blank=True)),
                ('slug', models.SlugField(help_text=b'The URL path that the visualization will map to (the slug)', max_length=75)),
                ('notes', models.TextField(help_text=b'Any notes that help explain the diagram, in Markdown format', blank=True)),
                ('degree_count', models.IntegerField(help_text=b'The number of degrees to display between cases')),
                ('view_count', models.IntegerField(default=0, help_text=b'The number of times the visualization has been seen.')),
                ('published', models.BooleanField(default=False, help_text=b'Whether the visualization can be seen publicly.')),
                ('deleted', models.BooleanField(default=False, help_text=b'Has a user chosen to delete this visualization?')),
                ('generation_time', models.FloatField(default=0, help_text=b'The length of time it takes to generate a visuzalization, in seconds.')),
                ('cluster_end', models.ForeignKey(related_name='visualizations_ending_here', to='search.OpinionCluster', help_text=b'The ending cluster for the visualization')),
                ('cluster_start', models.ForeignKey(related_name='visualizations_starting_here', to='search.OpinionCluster', help_text=b'The starting cluster for the visualization')),
                ('clusters', models.ManyToManyField(help_text=b'The clusters involved in this visualization', related_name='visualizations', to='search.OpinionCluster', blank=True)),
                ('user', models.ForeignKey(related_name='scotus_maps', to=settings.AUTH_USER_MODEL, help_text=b'The user that owns the visualization')),
            ],
        ),
        migrations.AddField(
            model_name='jsonversions',
            name='map',
            field=models.ForeignKey(related_name='json_versions', to='visualizations.SCOTUSMap', help_text=b'The visualization that the json is affiliated with.'),
        ),
    ]
