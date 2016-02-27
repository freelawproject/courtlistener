# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import cl.lib.model_helpers
import cl.lib.storage


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0001_initial'),
        ('people_db', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Audio',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('source', models.CharField(blank=True, help_text=b'the source of the audio file, one of: C (court website), R (public.resource.org), CR (court website merged with resource.org), L (lawbox), LC (lawbox merged with court), LR (lawbox merged with resource.org), LCR (lawbox merged with court and resource.org), M (manual input), A (internet archive), H (brad heath archive), Z (columbia archive), ZC (columbia merged with court), ZLC (columbia merged with lawbox and court), ZLR (columbia merged with lawbox and resource.org), ZLCR (columbia merged with lawbox, court, and resource.org), ZR (columbia merged with resource.org), ZCR (columbia merged with court and resource.org), ZL (columbia merged with lawbox)', max_length=10, choices=[(b'C', b'court website'), (b'R', b'public.resource.org'), (b'CR', b'court website merged with resource.org'), (b'L', b'lawbox'), (b'LC', b'lawbox merged with court'), (b'LR', b'lawbox merged with resource.org'), (b'LCR', b'lawbox merged with court and resource.org'), (b'M', b'manual input'), (b'A', b'internet archive'), (b'H', b'brad heath archive'), (b'Z', b'columbia archive'), (b'ZC', b'columbia merged with court'), (b'ZLC', b'columbia merged with lawbox and court'), (b'ZLR', b'columbia merged with lawbox and resource.org'), (b'ZLCR', b'columbia merged with lawbox, court, and resource.org'), (b'ZR', b'columbia merged with resource.org'), (b'ZCR', b'columbia merged with court and resource.org'), (b'ZL', b'columbia merged with lawbox')])),
                ('case_name_short', models.TextField(help_text=b"The abridged name of the case, often a single word, e.g. 'Marsh'", blank=True)),
                ('case_name', models.TextField(help_text=b'The full name of the case', blank=True)),
                ('case_name_full', models.TextField(help_text=b'The full name of the case', blank=True)),
                ('judges', models.TextField(help_text=b'The judges that heard the oral arguments as a simple text string. This field is used when normalized judges cannot be placed into the panel field.', null=True, blank=True)),
                ('date_created', models.DateTimeField(help_text=b'The original creation date for the item', db_index=True)),
                ('date_modified', models.DateTimeField(help_text=b'The last moment when the item was modified. A value in year 1750 indicates the value is unknown', db_index=True)),
                ('sha1', models.CharField(help_text=b'unique ID for the document, as generated via SHA1 of the binary file or text data', max_length=40, db_index=True)),
                ('download_url', models.URLField(help_text=b'The URL on the court website where the document was originally scraped', max_length=500, null=True, db_index=True, blank=True)),
                ('local_path_mp3', models.FileField(help_text=b'The location, relative to MEDIA_ROOT, on the CourtListener server, where encoded file is stored', upload_to=cl.lib.model_helpers.make_upload_path, storage=cl.lib.storage.IncrementingFileSystemStorage(), db_index=True, blank=True)),
                ('local_path_original_file', models.FileField(help_text=b'The location, relative to MEDIA_ROOT, on the CourtListener server, where the original file is stored', storage=cl.lib.storage.IncrementingFileSystemStorage(), upload_to=cl.lib.model_helpers.make_upload_path, db_index=True)),
                ('duration', models.SmallIntegerField(help_text=b'the length of the item, in seconds', null=True)),
                ('processing_complete', models.BooleanField(default=False, help_text=b'Is audio for this item done processing?')),
                ('date_blocked', models.DateField(help_text=b'The date that this opinion was blocked from indexing by search engines', null=True, db_index=True, blank=True)),
                ('blocked', models.BooleanField(default=False, help_text=b'Should this item be blocked from indexing by search engines?', db_index=True)),
                ('docket', models.ForeignKey(related_name='audio_files', blank=True, to='search.Docket', help_text=b'The docket that the oral argument is a part of', null=True)),
                ('panel', models.ManyToManyField(help_text=b'The judges that heard the oral arguments', related_name='oral_argument_panel_members', to='judges.Judge', blank=True)),
            ],
            options={
                'ordering': ['-date_created'],
                'verbose_name_plural': 'Audio Files',
            },
        ),
    ]
