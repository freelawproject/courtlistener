# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0063_add_pacer_rss_field'),
    ]

    operations = [
        migrations.CreateModel(
            name='RssFeedStatus',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('date_created', models.DateTimeField(help_text=b'The time when this item was created', auto_now_add=True, db_index=True)),
                ('date_modified', models.DateTimeField(help_text=b'The last moment when the item was modified.', auto_now=True, db_index=True)),
                ('date_last_build', models.DateTimeField(help_text=b'The dateLastBuilt field from the feed when it was visited.', null=True, blank=True)),
                ('status', models.SmallIntegerField(help_text=b'The current status of this feed. Possible values are: (1): Feed processed successfully., (2): Feed unchanged since last visit, (3): Feed encountered an error while processing., (4): Feed is currently being processed., (5): Feed failed processing, but will be retried.', db_index=True, choices=[(1, b'Feed processed successfully.'), (2, b'Feed unchanged since last visit'), (3, b'Feed encountered an error while processing.'), (4, b'Feed is currently being processed.'), (5, b'Feed failed processing, but will be retried.')])),
                ('court', models.ForeignKey(related_name='rss_feed_statuses', to='search.Court', help_text=b'The court where the upload was from')),
            ],
        ),
    ]
