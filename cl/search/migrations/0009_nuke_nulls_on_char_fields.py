# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models

import cl.lib.model_helpers
import cl.lib.storage


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0008_load_new_courts'),
        ('search', '0009_blankify_fields'),
    ]

    operations = [
        migrations.AlterField(
            model_name='docket',
            name='cause',
            field=models.CharField(default='', help_text=b'The cause for the case.', max_length=200, blank=True),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='docket',
            name='docket_number',
            field=models.CharField(default='', help_text=b'The docket numbers of a case, can be consolidated and quite long', max_length=5000, db_index=True, blank=True),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='docket',
            name='filepath_ia',
            field=models.CharField(default='', help_text=b'Path to the Docket XML page in The Internet Archive', max_length=1000, blank=True),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='docket',
            name='filepath_local',
            field=models.FileField(default='', upload_to=cl.lib.model_helpers.make_recap_path, storage=cl.lib.storage.IncrementingFileSystemStorage(), max_length=1000, blank=True, help_text=b"Path to RECAP's Docket XML page."),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='docket',
            name='jurisdiction_type',
            field=models.CharField(default='', help_text=b"Stands for jurisdiction in RECAP XML docket. For example, 'Diversity', 'U.S. Government Defendant'.", max_length=100, blank=True),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='docket',
            name='jury_demand',
            field=models.CharField(default='', help_text=b'The compensation demand.', max_length=500, blank=True),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='docket',
            name='nature_of_suit',
            field=models.CharField(default='', help_text=b'The nature of suit code from PACER.', max_length=100, blank=True),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='docket',
            name='slug',
            field=models.SlugField(default='', help_text=b'URL that the document should map to (the slug)', max_length=75, db_index=False, blank=True),
            preserve_default=False,
        ),
    ]
