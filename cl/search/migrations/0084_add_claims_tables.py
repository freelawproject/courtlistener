# -*- coding: utf-8 -*-
# Generated by Django 1.11.22 on 2019-08-01 21:48


import django.db.models.deletion
from django.db import migrations, models

import cl.lib.model_helpers
import cl.lib.storage


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0083_generate_docket_number_core'),
    ]

    operations = [
        migrations.CreateModel(
            name='BankruptcyInformation',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date_created', models.DateTimeField(auto_now_add=True, db_index=True, help_text='The date time this item was created.')),
                ('date_modified', models.DateTimeField(auto_now=True, db_index=True, help_text='Timestamp of last update.')),
                ('date_converted', models.DateTimeField(blank=True, help_text='The date when the bankruptcy was converted from one chapter to another.', null=True)),
                ('date_last_to_file_claims', models.DateTimeField(blank=True, help_text='The last date for filing claims.', null=True)),
                ('date_last_to_file_govt', models.DateTimeField(blank=True, help_text='The last date for the government to file claims.', null=True)),
                ('date_debtor_dismissed', models.DateTimeField(blank=True, help_text='The date the debtor was dismissed.', null=True)),
                ('chapter', models.CharField(blank=True, help_text='The chapter the bankruptcy is currently filed under.', max_length=10)),
                ('trustee_str', models.TextField(blank=True, help_text='The name of the trustee handling the case.')),
                ('docket', models.OneToOneField(help_text='The docket that the bankruptcy info is associated with.', on_delete=django.db.models.deletion.CASCADE, to='search.Docket')),
            ],
        ),
        migrations.CreateModel(
            name='Claim',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date_created', models.DateTimeField(auto_now_add=True, db_index=True, help_text='The date time this item was created.')),
                ('date_modified', models.DateTimeField(auto_now=True, db_index=True, help_text='Timestamp of last update.')),
                ('date_claim_modified', models.DateTimeField(blank=True, help_text='Date the claim was last modified to our knowledge.', null=True)),
                ('date_original_entered', models.DateTimeField(blank=True, help_text='Date the claim was originally entered.', null=True)),
                ('date_original_filed', models.DateTimeField(blank=True, help_text='Date the claim was originally filed.', null=True)),
                ('date_last_amendment_entered', models.DateTimeField(blank=True, help_text='Date the last amendment was entered.', null=True)),
                ('date_last_amendment_filed', models.DateTimeField(blank=True, help_text='Date the last amendment was filed.', null=True)),
                ('claim_number', models.CharField(blank=True, help_text='The number of the claim.', max_length=10)),
                ('creditor_details', models.TextField(blank=True, help_text='The details of the creditor from the claims register; typically their address.')),
                ('creditor_id', models.CharField(blank=True, help_text='The ID of the creditor from the claims register; typically a seven digit number', max_length=50)),
                ('status', models.CharField(blank=True, help_text='The status of the claim.', max_length=1000)),
                ('entered_by', models.CharField(blank=True, help_text='The person that entered the claim.', max_length=1000)),
                ('filed_by', models.CharField(blank=True, help_text='The person that filed the claim.', max_length=1000)),
                ('amount_claimed', models.CharField(blank=True, help_text='The amount claimed, usually in dollars.', max_length=100)),
                ('unsecured_claimed', models.CharField(blank=True, help_text='The unsecured claimed, usually in dollars.', max_length=100)),
                ('secured_claimed', models.CharField(blank=True, help_text='The secured claimed, usually in dollars.', max_length=100)),
                ('priority_claimed', models.CharField(blank=True, help_text='The priority claimed, usually in dollars.', max_length=100)),
                ('description', models.TextField(blank=True, help_text='The description of the claim that appears on the claim register.')),
                ('remarks', models.TextField(blank=True, help_text='The remarks of the claim that appear on the claim register.')),
                ('docket', models.ForeignKey(help_text='The docket that the claim is associated with.', on_delete=django.db.models.deletion.CASCADE, related_name='claims', to='search.Docket')),
                ('tags', models.ManyToManyField(blank=True, help_text='The tags associated with the document.', related_name='claims', to='search.Tag')),
            ],
        ),
        migrations.CreateModel(
            name='ClaimHistory',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date_created', models.DateTimeField(auto_now_add=True, db_index=True, help_text='The date the file was imported to Local Storage.')),
                ('date_modified', models.DateTimeField(auto_now=True, db_index=True, help_text='Timestamp of last update.')),
                ('date_upload', models.DateTimeField(blank=True, help_text='upload_date in RECAP. The date the file was uploaded to RECAP. This information is provided by RECAP.', null=True)),
                ('document_number', models.CharField(blank=True, db_index=True, help_text='If the file is a document, the number is the document_number in RECAP docket.', max_length=32)),
                ('attachment_number', models.SmallIntegerField(blank=True, help_text='If the file is an attachment, the number is the attachment number in RECAP docket.', null=True)),
                ('pacer_doc_id', models.CharField(blank=True, help_text='The ID of the document in PACER. This information is provided by RECAP.', max_length=32)),
                ('is_available', models.NullBooleanField(default=False, help_text='True if the item is available in RECAP')),
                ('sha1', models.CharField(blank=True, help_text='The ID used for a document in RECAP', max_length=40)),
                ('page_count', models.IntegerField(blank=True, help_text='The number of pages in the document, if known', null=True)),
                ('file_size', models.IntegerField(blank=True, help_text='The size of the file in bytes, if known', null=True)),
                ('filepath_local', models.FileField(blank=True, db_index=True, help_text='The path of the file in the local storage area.', max_length=1000, storage=cl.lib.storage.IncrementingFileSystemStorage(), upload_to=cl.lib.model_helpers.make_pdf_path)),
                ('filepath_ia', models.CharField(blank=True, help_text='The URL of the file in IA', max_length=1000)),
                ('ia_upload_failure_count', models.SmallIntegerField(blank=True, help_text='Number of times the upload to the Internet Archive failed.', null=True)),
                ('thumbnail', models.FileField(blank=True, help_text='A thumbnail of the first page of the document', null=True, storage=cl.lib.storage.IncrementingFileSystemStorage(), upload_to=cl.lib.model_helpers.make_recap_path)),
                ('thumbnail_status', models.SmallIntegerField(choices=[(0, 'Thumbnail needed'), (1, 'Thumbnail completed successfully'), (2, 'Unable to generate thumbnail')], default=0, help_text='The status of the thumbnail generation')),
                ('plain_text', models.TextField(blank=True, help_text='Plain text of the document after extraction using pdftotext, wpd2txt, etc.')),
                ('ocr_status', models.SmallIntegerField(blank=True, choices=[(1, 'OCR Complete'), (2, 'OCR Not Necessary'), (3, 'OCR Failed'), (4, 'OCR Needed')], help_text='The status of OCR processing on this item.', null=True)),
                ('is_free_on_pacer', models.NullBooleanField(db_index=True, help_text='Is this item freely available as an opinion on PACER?')),
                ('is_sealed', models.NullBooleanField(db_index=True, help_text='Is this item sealed or otherwise unavailable on PACER?')),
                ('date_filed', models.DateField(blank=True, help_text='The created date of the claim.', null=True)),
                ('claim_document_type', models.IntegerField(choices=[(1, 'A docket entry referenced from the claim register.'), (2, 'A document only referenced from the claim register')], help_text='The type of document that is used in the history row for the claim. One of: 1 (A docket entry referenced from the claim register.), 2 (A document only referenced from the claim register)')),
                ('description', models.TextField(blank=True, help_text='The text content of the docket entry that appears in the docket or claims registry page.')),
                ('claim_doc_id', models.CharField(blank=True, help_text='The ID of a claims registry document.', max_length=32)),
                ('pacer_dm_id', models.IntegerField(blank=True, help_text='The dm_id value pulled out of links and possibly other pages in PACER. Collected but not currently used.', null=True)),
                ('pacer_case_id', models.CharField(blank=True, help_text="The cased ID provided by PACER. Noted in this case on a per-document-level, since we've learned that some documents from other cases can appear in curious places.", max_length=100)),
                ('claim', models.ForeignKey(help_text='The claim that the history row is associated with.', on_delete=django.db.models.deletion.CASCADE, related_name='claims', to='search.Claim')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.AlterField(
            model_name='court',
            name='full_name',
            field=models.CharField(help_text='the full name of the court',
                                   max_length=200),
        ),
    ]
