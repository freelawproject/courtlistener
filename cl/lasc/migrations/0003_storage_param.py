# -*- coding: utf-8 -*-
# Generated by Django 1.11.27 on 2019-12-28 00:04


from django.db import migrations, models

import cl.lib.model_helpers
import cl.lib.storage


class Migration(migrations.Migration):

    dependencies = [
        ('lasc', '0002_auto_20191004_1431'),
    ]

    operations = [
        migrations.AlterField(
            model_name='lascpdf',
            name='filepath_s3',
            field=models.FileField(blank=True, help_text='The path of the file in the s3 bucket.', max_length=150, storage=cl.lib.storage.AWSMediaStorage(), upload_to=cl.lib.model_helpers.make_pdf_path),
        ),
    ]
