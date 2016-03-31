# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import cl.lib.model_helpers
import cl.lib.storage


class Migration(migrations.Migration):

    dependencies = [
        ('people_db', '0006_person_cl_id'),
        ('search', '0002_load_initial_data'),
    ]

    operations = [
        migrations.CreateModel(
            name='DocketEntry',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('date_created', models.DateTimeField(help_text=b'The time when this item was created.', auto_now_add=True, db_index=True)),
                ('date_modified', models.DateTimeField(help_text=b'The last moment when the item was modified.', auto_now=True, db_index=True)),
                ('date_filed', models.DateField(help_text=b'The created date of the Docket Entry.')),
                ('entry_number', models.PositiveIntegerField(help_text=b'# on the PACER docket page.')),
                ('description', models.TextField(help_text=b'The text content of the docket entry that appears in the PACER docket page.', db_index=True)),
            ],
        ),
        migrations.CreateModel(
            name='RECAPDocument',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('date_created', models.DateTimeField(help_text=b'The date the file was imported to Local Storage.', auto_now_add=True, db_index=True)),
                ('date_modified', models.DateTimeField(help_text=b'Timestamp of last update.', auto_now=True, db_index=True)),
                ('date_upload', models.DateTimeField(help_text=b'upload_date in RECAP. The date the file was uploaded to RECAP. This information is provided by RECAP.', null=True, blank=True)),
                ('document_type', models.IntegerField(help_text=b'Whether this is a regular document or an attachment.', db_index=True, choices=[(1, b'PACER Document'), (2, b'Attachment')])),
                ('document_number', models.PositiveIntegerField(help_text=b'If the file is a document, the number is the document_number in RECAP docket.')),
                ('attachment_number', models.SmallIntegerField(help_text=b'If the file is an attachment, the number is the attachment number in RECAP docket.', null=True, blank=True)),
                ('pacer_doc_id', models.CharField(help_text=b'The ID of the document in PACER. This information is provided by RECAP.', unique=True, max_length=32)),
                ('is_available', models.NullBooleanField(default=False, help_text=b'True if the item is available in RECAP')),
                ('sha1', models.CharField(help_text=b'The ID used for a document in RECAP', max_length=40, blank=True)),
                ('filepath_local', models.FileField(help_text=b'The path of the file in the local storage area.', storage=cl.lib.storage.IncrementingFileSystemStorage(), max_length=1000, upload_to=cl.lib.model_helpers.make_recap_path)),
                ('filepath_ia', models.CharField(help_text=b'The URL of the file in IA', max_length=1000)),
                ('docket_entry', models.ForeignKey(help_text=b'Foreign Key to the DocketEntry object to which it belongs. Multiple documents can belong to a DocketEntry. (Attachments and Documents together)', to='search.DocketEntry')),
            ],
        ),
        migrations.AddField(
            model_name='docket',
            name='assigned_to',
            field=models.ForeignKey(related_name='assigning', to='people_db.Person', help_text=b'The judge the case was assigned to.', null=True),
        ),
        migrations.AddField(
            model_name='docket',
            name='cause',
            field=models.CharField(help_text=b'The cause for the case.', max_length=200, null=True, blank=True),
        ),
        migrations.AddField(
            model_name='docket',
            name='date_filed',
            field=models.DateField(help_text=b'The date the case was filed.', null=True, blank=True),
        ),
        migrations.AddField(
            model_name='docket',
            name='date_last_filing',
            field=models.DateField(help_text=b'The date the case was last updated in the docket. ', null=True, blank=True),
        ),
        migrations.AddField(
            model_name='docket',
            name='date_terminated',
            field=models.DateField(help_text=b'The date the case was terminated.', null=True, blank=True),
        ),
        migrations.AddField(
            model_name='docket',
            name='filepath_ia',
            field=models.CharField(help_text=b'Path to the Docket XML page in The Internet Archive', max_length=1000, null=True, blank=True),
        ),
        migrations.AddField(
            model_name='docket',
            name='filepath_local',
            field=models.FileField(upload_to=cl.lib.model_helpers.make_recap_path, storage=cl.lib.storage.IncrementingFileSystemStorage(), max_length=1000, blank=True, help_text=b'Path to RECAP\'s Docket XML page.', null=True),
        ),
        migrations.AddField(
            model_name='docket',
            name='jurisdiction_type',
            field=models.CharField(help_text=b"Stands for jurisdiction in RECAP XML docket. For example, 'Diversity', 'U.S. Government Defendant'.", max_length=100, null=True, blank=True),
        ),
        migrations.AddField(
            model_name='docket',
            name='jury_demand',
            field=models.CharField(help_text=b'The compensation demand.', max_length=500, null=True, blank=True),
        ),
        migrations.AddField(
            model_name='docket',
            name='nature_of_suit',
            field=models.CharField(help_text=b'The nature of suit code from PACER.', max_length=100, null=True, blank=True),
        ),
        migrations.AddField(
            model_name='docket',
            name='pacer_case_id',
            field=models.PositiveIntegerField(help_text=b'The cased ID provided by PACER.', null=True, db_index=True, blank=True),
        ),
        migrations.AddField(
            model_name='docket',
            name='referred_to',
            field=models.ForeignKey(related_name='referring', to='people_db.Person', help_text=b"The judge to whom the 'assigned_to' judge is delegated. (Not verified)", null=True),
        ),
        migrations.AddField(
            model_name='docket',
            name='source',
            field=models.SmallIntegerField(default=0, help_text=b'contains the source of the Docket.', choices=[(0, b'Default'), (1, b'RECAP')]),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='docket',
            name='docket_number',
            field=models.CharField(help_text=b'The docket numbers of a case, can be consolidated and quite long', max_length=5000, null=True, db_index=True, blank=True),
        ),
        migrations.AlterUniqueTogether(
            name='docket',
            unique_together={('court', 'pacer_case_id')},
        ),
        migrations.AddField(
            model_name='docketentry',
            name='docket',
            field=models.ForeignKey(help_text=b'Foreign key as a relation to the corresponding Docket object. Specifies which docket the docket entry belongs to.', to='search.Docket'),
        ),
        migrations.AlterUniqueTogether(
            name='recapdocument',
            unique_together={('docket_entry', 'document_number',
                              'attachment_number')},
        ),
        migrations.AlterUniqueTogether(
            name='docketentry',
            unique_together={('docket', 'entry_number')},
        ),
    ]
