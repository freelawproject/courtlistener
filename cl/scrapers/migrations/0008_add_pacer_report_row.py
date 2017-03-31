# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('scrapers', '0007_load_pacer_free_opinions_initial_data'),
    ]

    operations = [
        migrations.CreateModel(
            name='PACERFreeDocumentRow',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('court_id', models.CharField(max_length=15)),
                ('pacer_case_id', models.CharField(max_length=100)),
                ('docket_number', models.CharField(max_length=5000)),
                ('case_name', models.TextField()),
                ('date_filed', models.DateField()),
                ('pacer_doc_id', models.CharField(unique=True, max_length=32)),
                ('document_number', models.CharField(max_length=32)),
                ('description', models.TextField()),
                ('nature_of_suit', models.TextField()),
                ('cause', models.CharField(max_length=2000)),
            ],
        ),
    ]
