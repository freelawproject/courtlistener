# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('judges', '0007_auto_20151230_1709'),
        ('search', '0011_auto_20151222_1240'),
    ]

    operations = [
        migrations.CreateModel(
            name='DocketEntry',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('filed_date', models.DateField(help_text=b'The Created date of the Docket Entry.')),
                ('entered_date', models.DateField(help_text=b'The date the Docket entry was entered in RECAP. Found in RECAP.', null=True, blank=True)),
                ('entry_number', models.PositiveIntegerField(help_text=b'# on the PACER docket page.')),
                ('text', models.TextField(help_text=b'The text content of the docket entry that appears in the PACER docket page. This field is the long_desc in RECAP.', db_index=True)),
            ],
        ),
        migrations.CreateModel(
            name='Document',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('document_type', models.IntegerField(help_text=b'The type of file. Should be an enumeration.(Whether it is a Document or Attachment).', db_index=True, choices=[(1, b'PACER Document'), (2, b'Attachment')])),
                ('document_number', models.PositiveIntegerField(help_text=b'If the file is a document, the number is the document_number in RECAP docket.')),
                ('attachment_number', models.PositiveIntegerField(help_text=b'If the file is an attachment, the number is the attachment number in RECAP docket.', null=True, blank=True)),
                ('pacer_doc_id', models.CharField(help_text=b'The ID of the document in PACER. This information is provided by RECAP.', max_length=32, null=True, blank=True)),
                ('date_upload', models.DateTimeField(help_text=b'upload_date in RECAP. The date the file was uploaded to RECAP. This information is provided by RECAP.', null=True, blank=True)),
                ('is_available', models.SmallIntegerField(default=0, help_text=b'Boolean (0 or 1) value to say if the document is available in RECAP.', null=True, blank=True)),
                ('free_import', models.SmallIntegerField(default=0, help_text=b'Found in RECAP. Says if the document is free.', null=True, blank=True)),
                ('sha1', models.CharField(help_text=b'The ID used for a document in RECAP', max_length=40, null=True, blank=True)),
                ('filepath_local', models.FilePathField(help_text=b' The path of the file in the local storage area.', max_length=500)),
                ('filepath_ia', models.FilePathField(help_text=b' The URL of the file in IA', max_length=500)),
                ('date_created', models.DateTimeField(help_text=b'The date the file was imported to Local Storage.', null=True, blank=True)),
                ('date_modified', models.DateTimeField(help_text=b'The date the Document object was last updated in CourtListener', null=True, blank=True)),
                ('docket_entry', models.ForeignKey(help_text=b'Foreign Key to the DocketEntry object to which it belongs. Multiple documents can belong to a DocketEntry. (Attachments and Documents together)', to='search.DocketEntry')),
            ],
        ),
        migrations.AddField(
            model_name='docket',
            name='assigned_to',
            field=models.ForeignKey(to='judges.Judge', help_text=b'The judge the case was assigned to.', null=True),
        ),
        migrations.AddField(
            model_name='docket',
            name='case_cause',
            field=models.CharField(help_text=b' The type of cause for the case (Not sure)', max_length=200, null=True, blank=True),
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
            name='jurisdiction_type',
            field=models.CharField(help_text=b'Stands for jurisdiction in RECAP XML docket.', max_length=100, null=True, blank=True),
        ),
        migrations.AddField(
            model_name='docket',
            name='jury_demand',
            field=models.CharField(help_text=b'The compensation demand (Not sure)', max_length=500, null=True, blank=True),
        ),
        migrations.AddField(
            model_name='docket',
            name='nature_of_suit',
            field=models.CharField(help_text=b' The type of case.  (Not sure)', max_length=100, null=True, blank=True),
        ),
        migrations.AddField(
            model_name='docket',
            name='pacer_case_id',
            field=models.PositiveIntegerField(help_text=b'The cased ID which PACER provides.', null=True, db_index=True, blank=True),
        ),
        migrations.AddField(
            model_name='docket',
            name='source',
            field=models.SmallIntegerField(default=0, help_text=b'contains the source of the Docket.', choices=[(0, b'Default'), (1, b'Recap')]),
        ),
        migrations.AddField(
            model_name='docket',
            name='xml_filepath_ia',
            field=models.FilePathField(help_text=b'The Docket XML page file path in The Internet Archive', max_length=500, null=True, blank=True),
        ),
        migrations.AddField(
            model_name='docket',
            name='xml_filepath_local',
            field=models.FilePathField(help_text=b'RECAP\xe2\x80\x99s Docket XML page file path in the local storage area.', max_length=500, null=True, blank=True),
        ),
        migrations.AlterField(
            model_name='docket',
            name='docket_number',
            field=models.CharField(help_text=b'The docket numbers of a case, can be consolidated and quite long', max_length=5000, db_index=True, null=False, blank=False),
        ),
        migrations.AddField(
            model_name='docketentry',
            name='docket',
            field=models.ForeignKey(help_text=b'Foreign key as a relation to the corresponding Docket object. Specifies which docket the docket entry belongs to.', to='search.Docket'),
        ),
    ]
