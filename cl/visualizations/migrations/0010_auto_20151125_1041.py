# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('visualizations', '0009_referer'),
    ]

    operations = [
        migrations.AlterField(
            model_name='referer',
            name='page_title',
            field=models.CharField(help_text=b'The title of the page where the item was embedded', max_length=500, blank=True),
        ),
        migrations.AlterField(
            model_name='referer',
            name='url',
            field=models.URLField(help_text=b'The URL where this item was embedded.', max_length=b'3000', db_index=True),
        ),
        migrations.AlterUniqueTogether(
            name='referer',
            unique_together=set([('map', 'url')]),
        ),
    ]
