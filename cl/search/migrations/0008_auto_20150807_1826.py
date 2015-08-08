# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import datetime
from django.utils.timezone import utc


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0007_auto_20150805_1733'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='opinion',
            name='time_retrieved',
        ),
        migrations.AddField(
            model_name='docket',
            name='date_created',
            field=models.DateTimeField(default=datetime.datetime(2015, 8, 8, 1, 25, 31, 529257, tzinfo=utc), help_text=b'The time when this item was created', db_index=True),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='opinion',
            name='date_created',
            field=models.DateTimeField(default=datetime.datetime(2015, 8, 8, 1, 25, 35, 321301, tzinfo=utc), help_text=b'The original creation date for the item', db_index=True),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='opinioncluster',
            name='date_created',
            field=models.DateTimeField(default=datetime.datetime(2015, 8, 8, 1, 25, 39, 65298, tzinfo=utc), help_text=b'The time when this item was created', db_index=True),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='court',
            name='date_modified',
            field=models.DateTimeField(default=datetime.datetime(2015, 8, 8, 1, 26, 3, 513110, tzinfo=utc), help_text=b'The last moment when the item was modified', db_index=True),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='docket',
            name='date_modified',
            field=models.DateTimeField(default=datetime.datetime(2015, 8, 8, 1, 26, 17, 688791, tzinfo=utc), help_text=b'The last moment when the item was modified. A value in year 1750 indicates the value is unknown', db_index=True),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='opinion',
            name='date_modified',
            field=models.DateTimeField(default=datetime.datetime(2015, 8, 8, 1, 26, 32, 88759, tzinfo=utc), help_text=b'The last moment when the item was modified. A value in year 1750 indicates the value is unknown', db_index=True),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='opinioncluster',
            name='date_modified',
            field=models.DateTimeField(help_text=b'The last moment when the item was modified. A value in year 1750 indicates the value is unknown', db_index=True),
        ),
        migrations.AlterField(
            model_name='opinioncluster',
            name='panel',
            field=models.ManyToManyField(help_text=b'The judges that heard the oral arguments', related_name='opinion_clusters_participating_judges', to='judges.Judge', blank=True),
        ),
    ]
