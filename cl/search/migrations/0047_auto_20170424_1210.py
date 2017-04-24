# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0046_auto_20170313_1424'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='docketentry',
            options={'ordering': ('entry_number',), 'verbose_name_plural': 'Docket Entries', 'permissions': (('has_recap_api_access', 'Can work with RECAP API'),)},
        ),
        migrations.AlterModelOptions(
            name='recapdocument',
            options={'ordering': ('document_number', 'attachment_number'), 'permissions': (('has_recap_api_access', 'Can work with RECAP API'),)},
        ),
    ]
