# Generated by Django 3.1.7 on 2021-05-28 19:34

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('recap', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('contenttypes', '0002_remove_content_type_name'),
        ('search', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='processingqueue',
            name='court',
            field=models.ForeignKey(help_text='The court where the upload was from', on_delete=django.db.models.deletion.CASCADE, related_name='recap_processing_queue', to='search.court'),
        ),
        migrations.AddField(
            model_name='processingqueue',
            name='docket',
            field=models.ForeignKey(help_text='The docket that was created or updated by this request.', null=True, on_delete=django.db.models.deletion.CASCADE, to='search.docket'),
        ),
        migrations.AddField(
            model_name='processingqueue',
            name='docket_entry',
            field=models.ForeignKey(help_text='The docket entry that was created or updated by this request, if applicable. Only applies to PDFs uploads.', null=True, on_delete=django.db.models.deletion.CASCADE, to='search.docketentry'),
        ),
        migrations.AddField(
            model_name='processingqueue',
            name='recap_document',
            field=models.ForeignKey(help_text='The document that was created or updated by this request, if applicable. Only applies to PDFs uploads.', null=True, on_delete=django.db.models.deletion.CASCADE, to='search.recapdocument'),
        ),
        migrations.AddField(
            model_name='processingqueue',
            name='uploader',
            field=models.ForeignKey(help_text='The user that uploaded the item to RECAP.', on_delete=django.db.models.deletion.CASCADE, related_name='recap_processing_queue', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='pacerhtmlfiles',
            name='content_type',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='contenttypes.contenttype'),
        ),
        migrations.AddField(
            model_name='pacerfetchqueue',
            name='court',
            field=models.ForeignKey(help_text='The court where the request will be made', null=True, on_delete=django.db.models.deletion.CASCADE, related_name='pacer_fetch_queue_items', to='search.court'),
        ),
        migrations.AddField(
            model_name='pacerfetchqueue',
            name='docket',
            field=models.ForeignKey(help_text='The ID of an existing docket object in the CourtListener database that should be updated.', null=True, on_delete=django.db.models.deletion.CASCADE, related_name='pacer_fetch_queue_items', to='search.docket'),
        ),
        migrations.AddField(
            model_name='pacerfetchqueue',
            name='recap_document',
            field=models.ForeignKey(help_text='The ID of the RECAP Document in the CourtListener databae that you wish to fetch or update.', null=True, on_delete=django.db.models.deletion.CASCADE, related_name='pacer_fetch_queue_items', to='search.recapdocument'),
        ),
        migrations.AddField(
            model_name='pacerfetchqueue',
            name='user',
            field=models.ForeignKey(help_text='The user that made the request.', on_delete=django.db.models.deletion.CASCADE, related_name='pacer_fetch_queue_items', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='fjcintegrateddatabase',
            name='circuit',
            field=models.ForeignKey(blank=True, help_text='Circuit in which the case was filed.', null=True, on_delete=django.db.models.deletion.CASCADE, related_name='+', to='search.court'),
        ),
        migrations.AddField(
            model_name='fjcintegrateddatabase',
            name='district',
            field=models.ForeignKey(blank=True, help_text='District court in which the case was filed.', null=True, on_delete=django.db.models.deletion.CASCADE, related_name='idb_cases', to='search.court'),
        ),
        migrations.AddField(
            model_name='emailprocessingqueue',
            name='court',
            field=models.ForeignKey(help_text='The court where the upload was from', on_delete=django.db.models.deletion.CASCADE, related_name='recap_email_processing_queue', to='search.court'),
        ),
        migrations.AddField(
            model_name='emailprocessingqueue',
            name='recap_documents',
            field=models.ManyToManyField(help_text='Document(s) created from the PACER email, processed as a function of this queue.', related_name='recap_email_processing_queue', to='search.RECAPDocument'),
        ),
        migrations.AddField(
            model_name='emailprocessingqueue',
            name='uploader',
            field=models.ForeignKey(help_text='The user that sent in the email for processing.', on_delete=django.db.models.deletion.CASCADE, related_name='recap_email_processing_queue', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddIndex(
            model_name='fjcintegrateddatabase',
            index=models.Index(fields=['district', 'docket_number'], name='recap_fjcintegrateddatabase_district_id_455568623a9da568_idx'),
        ),
    ]
