# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0056_add_fjc_court_id_values'),
    ]

    operations = [
        migrations.AddField(
            model_name='docket',
            name='tags',
            field=models.ManyToManyField(help_text=b'The tags associated with the docket.', related_name='dockets', to='search.Tag', blank=True),
        ),
        migrations.AddField(
            model_name='docketentry',
            name='tags',
            field=models.ManyToManyField(help_text=b'The tags associated with the docket entry.', related_name='docket_entries', to='search.Tag', blank=True),
        ),
    ]
