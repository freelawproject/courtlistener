# -*- coding: utf-8 -*-
# Generated by Django 1.11.29 on 2020-12-31 19:24
from __future__ import unicode_literals

import cl.disclosures.models
import cl.lib.storage
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('disclosures', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='financialdisclosure',
            name='filepath',
            field=models.FileField(db_index=True, help_text='The filepath to the disclosure normalized to a PDF.', max_length=300, storage=cl.lib.storage.AWSMediaStorage(), upload_to=cl.disclosures.models.pdf_path),
        ),
        migrations.AlterField(
            model_name='financialdisclosure',
            name='thumbnail',
            field=models.FileField(blank=True, help_text='A thumbnail of the first page of the disclosure form.', max_length=300, null=True, storage=cl.lib.storage.AWSMediaStorage(), upload_to=cl.disclosures.models.thumbnail_path),
        ),
    ]
