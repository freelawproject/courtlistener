# -*- coding: utf-8 -*-


from django.conf import settings
from django.db import migrations, models

import cl.lib.storage
import cl.recap.models


def get_related_name():
    return 'recap_email_processing_queue'

class Migration(migrations.Migration):

    dependencies = [
        ('recap', '0031_abstract_datetime_model',)
    ]

    operations = [
        migrations.CreateModel(
            name='EmailProcessingQueue',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('date_created', models.DateTimeField(help_text='The time when this item was created', auto_now_add=True, db_index=True)),
                ('date_modified', models.DateTimeField(help_text='The last moment when the item was modified.', auto_now=True, db_index=True)),
                ('filepath', models.FileField(help_text='The S3 filepath to the email and receipt stored as JSON text.', storage=cl.lib.storage.AWSMediaStorage(), max_length=1000, upload_to=cl.recap.models.make_recap_email_processing_queue_aws_path)),
                ('status', models.SmallIntegerField(help_text='The current status of this upload.', choices=[(1, 'Awaiting processing in queue.'), (2, 'Item processed successfully.'), (3, 'Item encountered an error while processing.'), (4, 'Item is currently being processed.'), (5, 'Item failed processing, but will be retried.')])),
                ('status_message', models.TextField(help_text='Any errors that occurred while processing an item', blank=True)),
                ('court', models.ForeignKey(related_name=get_related_name(), to='search.Court', help_text='The court where the upload was from',
                                            on_delete=models.CASCADE)),
                ('uploader', models.ForeignKey(related_name=get_related_name(), to=settings.AUTH_USER_MODEL, help_text='The user that uploaded the item to RECAP.',
                                               on_delete=models.CASCADE)),
                ('recap_documents', models.ManyToManyField(related_name=get_related_name(), to='search.RECAPDocument', help_text="Document(s) created as a result of processing this request.", null=True)),
            ],
        ),
    ]
