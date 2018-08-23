# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0068_add_mdl_fields'),
    ]

    operations = [
        migrations.AlterIndexTogether(
            name='recapdocument',
            index_together=set([('document_type', 'document_number', 'attachment_number')]),
        ),
    ]
