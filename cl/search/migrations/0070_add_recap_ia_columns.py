# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0069_add_rd_multicolumn_index'),
    ]

    operations = [
        migrations.AddField(
            model_name='docket',
            name='filepath_ia_json',
            field=models.CharField(help_text=b'Path to the docket JSON page in the Internet Archive', max_length=1000, blank=True),
        ),
        migrations.AddField(
            model_name='docket',
            name='ia_date_first_change',
            field=models.DateTimeField(help_text=b'The moment when this item first changed and was marked as needing an upload. Used for determining when to upload an item.', null=True, db_index=True),
        ),
        migrations.AddField(
            model_name='docket',
            name='ia_needs_upload',
            field=models.NullBooleanField(help_text=b"Does this item need to be uploaded to the Internet Archive? I.e., has it changed? This field is important because it keeps track of the status of all the related objects to the docket. For example, if a related docket entry changes, we need to upload the item to IA, but we can't easily check that.", db_index=True),
        ),
        migrations.AddField(
            model_name='docket',
            name='ia_upload_failure_count',
            field=models.SmallIntegerField(help_text=b'Number of times the upload to the Internet Archive failed.', null=True, blank=True),
        ),
    ]
