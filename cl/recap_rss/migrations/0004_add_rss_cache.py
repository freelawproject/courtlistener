# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('recap_rss', '0003_auto_20180430_2200'),
    ]

    operations = [
        migrations.CreateModel(
            name='RssItemCache',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('date_created', models.DateTimeField(help_text=b'The time when this item was created', auto_now_add=True, db_index=True)),
                ('hash', models.CharField(unique=True, max_length=64, db_index=True)),
            ],
        ),
    ]
