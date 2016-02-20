# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('visualizations', '0008_scotusmap_date_deleted'),
    ]

    operations = [
        migrations.CreateModel(
            name='Referer',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('date_created', models.DateTimeField(help_text=b'The time when this item was created', auto_now_add=True, db_index=True)),
                ('date_modified', models.DateTimeField(help_text=b'The time when this item was modified', auto_now=True, db_index=True)),
                ('url', models.URLField(help_text=b'The URL where this item was embedded.', unique=True, max_length=b'3000', db_index=True)),
                ('page_title', models.URLField(help_text=b'The title of the page where the item was embedded')),
                ('display', models.BooleanField(default=False, help_text=b'Should this item be displayed?')),
                ('map', models.ForeignKey(related_name='referers', to='visualizations.SCOTUSMap', help_text=b'The visualization that was embedded and which generated a referer')),
            ],
        ),
    ]
