# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0052_auto_20170720_1309'),
        ('recap', '0002_auto_20170809_1453'),
    ]

    operations = [
        migrations.AddField(
            model_name='processingqueue',
            name='docket',
            field=models.ForeignKey(to='search.Docket', help_text=b'The docket that was created or updated by this request.', null=True),
        ),
        migrations.AddField(
            model_name='processingqueue',
            name='docket_entry',
            field=models.ForeignKey(to='search.DocketEntry', help_text=b'The docket entry that was created or updated by this request, if applicable. Only applies to PDFs uploads.', null=True),
        ),
        migrations.AddField(
            model_name='processingqueue',
            name='recap_document',
            field=models.ForeignKey(to='search.RECAPDocument', help_text=b'The document that was created or updated by this request, if applicable. Only applies to PDFs uploads.', null=True),
        ),
    ]
