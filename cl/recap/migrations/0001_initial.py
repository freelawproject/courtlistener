# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
from django.conf import settings
import cl.recap.models
import cl.lib.storage


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('search', '0047_auto_20170424_1210'),
    ]

    operations = [
        migrations.CreateModel(
            name='ProcessingQueue',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('date_created', models.DateTimeField(help_text=b'The time when this item was created', auto_now_add=True, db_index=True)),
                ('date_modified', models.DateTimeField(help_text=b'The last moment when the item was modified.', auto_now=True, db_index=True)),
                ('pacer_case_id', models.CharField(help_text=b'The cased ID provided by PACER.', max_length=100)),
                ('pacer_doc_id', models.CharField(help_text=b'The ID of the document in PACER. This information is provided by RECAP.', unique=True, max_length=32, blank=True)),
                ('document_number', models.CharField(help_text=b'If the file is a document, the number is the document_number in RECAP docket.', max_length=32)),
                ('attachment_number', models.SmallIntegerField(help_text=b'If the file is an attachment, the number is the attachment number in RECAP docket.', null=True, blank=True)),
                ('filepath_local', models.FileField(help_text=b'The path of the uploaded file.', storage=cl.lib.storage.UUIDFileSystemStorage(), max_length=1000, upload_to=cl.recap.models.make_recap_processing_queue_path)),
                ('status', models.SmallIntegerField(help_text=b'The current status of this upload.', choices=[(1, b'Awaiting processing in queue.'), (2, b'Item processed successfully.'), (3, b'Item encountered an error while processing.'), (4, b'Item is currently being processed.'), (5, b'Item failed processing, but will be retried.')])),
                ('upload_type', models.SmallIntegerField(help_text=b'The type of object that is uploaded', choices=[(1, b'HTML Docket'), (2, b'HTML attachment page'), (3, b'PDF')])),
                ('error_message', models.TextField(help_text=b'Any errors that occurred while processing an item', blank=True)),
                ('court', models.ForeignKey(related_name='recap_processing_queue', to='search.Court', help_text=b'The court where the upload was from')),
                ('uploader', models.ForeignKey(related_name='recap_processing_queue', to=settings.AUTH_USER_MODEL, help_text=b'The user that uploaded the item to RECAP.')),
            ],
            options={
                'permissions': (('has_recap_upload_access', 'Can upload documents to RECAP.'),),
            },
        ),
    ]
