# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0052_auto_20170720_1309'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='recapdocument',
            options={'ordering': ('document_type', 'document_number', 'attachment_number'), 'permissions': (('has_recap_api_access', 'Can work with RECAP API'),)},
        ),
    ]
