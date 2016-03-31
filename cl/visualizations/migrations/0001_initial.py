# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='JSONVersion',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('date_created', models.DateTimeField(help_text=b'The time when this item was created', auto_now_add=True, db_index=True)),
                ('date_modified', models.DateTimeField(help_text=b'The last moment when the item was modified.', auto_now=True, db_index=True)),
                ('json_data', models.TextField(help_text=b'The JSON data for a particular version of the visualization.')),
            ],
            options={
                'ordering': ['-date_modified'],
            },
        ),
        migrations.CreateModel(
            name='Referer',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('date_created', models.DateTimeField(help_text=b'The time when this item was created', auto_now_add=True, db_index=True)),
                ('date_modified', models.DateTimeField(help_text=b'The time when this item was modified', auto_now=True, db_index=True)),
                ('url', models.URLField(help_text=b'The URL where this item was embedded.', max_length=b'3000', db_index=True)),
                ('page_title', models.CharField(help_text=b'The title of the page where the item was embedded', max_length=500, blank=True)),
                ('display', models.BooleanField(default=False, help_text=b'Should this item be displayed?')),
            ],
        ),
        migrations.CreateModel(
            name='SCOTUSMap',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('date_created', models.DateTimeField(help_text=b'The time when this item was created', auto_now_add=True, db_index=True)),
                ('date_modified', models.DateTimeField(help_text=b'The last moment when the item was modified.', auto_now=True, db_index=True)),
                ('date_published', models.DateTimeField(help_text=b'The moment when the visualization was first shared', null=True, db_index=True, blank=True)),
                ('date_deleted', models.DateTimeField(help_text=b'The moment when the visualization was last deleted', null=True, db_index=True, blank=True)),
                ('title', models.CharField(help_text=b"The title of the visualization that you're creating.", max_length=200)),
                ('slug', models.SlugField(help_text=b'The URL path that the visualization will map to (the slug)', max_length=75)),
                ('notes', models.TextField(help_text=b'A description to help explain the diagram, in Markdown format', blank=True)),
                ('view_count', models.IntegerField(default=0, help_text=b'The number of times the visualization has been seen.')),
                ('published', models.BooleanField(default=False, help_text=b'Whether the visualization has been shared.')),
                ('deleted', models.BooleanField(default=False, help_text=b'Has a user chosen to delete this visualization?')),
                ('generation_time', models.FloatField(default=0, help_text=b'The length of time it takes to generate a visuzalization, in seconds.')),
                ('cluster_end', models.ForeignKey(related_name='visualizations_ending_here', to='search.OpinionCluster', help_text=b'The ending cluster for the visualization')),
                ('cluster_start', models.ForeignKey(related_name='visualizations_starting_here', to='search.OpinionCluster', help_text=b'The starting cluster for the visualization')),
                ('clusters', models.ManyToManyField(help_text=b'The clusters involved in this visualization, including the start and end clusters.', related_name='visualizations', to='search.OpinionCluster', blank=True)),
                ('user', models.ForeignKey(related_name='scotus_maps', to=settings.AUTH_USER_MODEL, help_text=b'The user that owns the visualization')),
            ],
        ),
        migrations.AddField(
            model_name='referer',
            name='map',
            field=models.ForeignKey(related_name='referers', to='visualizations.SCOTUSMap', help_text=b'The visualization that was embedded and which generated a referer'),
        ),
        migrations.AddField(
            model_name='jsonversion',
            name='map',
            field=models.ForeignKey(related_name='json_versions', to='visualizations.SCOTUSMap', help_text=b'The visualization that the json is affiliated with.'),
        ),
        migrations.AlterUniqueTogether(
            name='referer',
            unique_together=set([('map', 'url')]),
        ),
    ]
