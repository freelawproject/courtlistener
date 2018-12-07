# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0080_minute_entries'),
    ]

    operations = [
        migrations.AlterField(
            model_name='docketentry',
            name='pacer_sequence_number',
            field=models.IntegerField(help_text=b'The de_seqno value pulled out of dockets, RSS feeds, and sundry other pages in PACER. The place to find this is currently in the onclick attribute of the links in PACER. Because we do not have this value for all items in the DB, we do not use this value for anything. Still, we collect it for good measure.', null=True, db_index=True, blank=True),
        ),
    ]
