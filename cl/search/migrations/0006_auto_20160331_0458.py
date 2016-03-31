# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0005_allow_blank_fks_in_docket'),
    ]

    operations = [
        migrations.CreateModel(
            name='CaseParties',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('name_first', models.CharField(help_text=b'First name', max_length=500, blank=True)),
                ('name_last', models.CharField(help_text=b'Last name', max_length=500, blank=True)),
                ('name_middle', models.CharField(help_text=b'Middle name', max_length=500, blank=True)),
                ('name_suffix', models.CharField(help_text=b'Suffix name', max_length=500, blank=True)),
                ('role', models.CharField(help_text=b'Parties role in the case', max_length=500, blank=True)),
            ],
        ),
        migrations.AddField(
            model_name='docket',
            name='fdsys_case_id',
            field=models.CharField(help_text=b'The cased ID provided by FDSYS.', max_length=100, null=True, db_index=True, blank=True),
        ),
        migrations.AddField(
            model_name='docket',
            name='fdsys_url',
            field=models.CharField(help_text=b'Path to the Docket XML page in FDSYS site', max_length=1000, null=True, blank=True),
        ),
        migrations.AddField(
            model_name='docket',
            name='sha1',
            field=models.CharField(help_text=b'Used for FDSYS dockets', max_length=40, blank=True),
        ),
        migrations.AddField(
            model_name='docketentry',
            name='fdsys_entry_number',
            field=models.PositiveIntegerField(help_text=b'# on the FDSYS docket page.', null=True),
        ),
        migrations.AddField(
            model_name='recapdocument',
            name='fdsys_url',
            field=models.CharField(help_text=b'The URL of the file in FDSYS', max_length=1000, null=True),
        ),
        migrations.AlterField(
            model_name='docket',
            name='source',
            field=models.SmallIntegerField(help_text=b'contains the source of the Docket.', choices=[(0, b'Default'), (1, b'RECAP'), (2, b'Scraper'), (3, b'FDSYS')]),
        ),
        migrations.AlterField(
            model_name='docketentry',
            name='entry_number',
            field=models.PositiveIntegerField(help_text=b'# on the PACER docket page.', null=True),
        ),
        migrations.AlterField(
            model_name='recapdocument',
            name='document_number',
            field=models.PositiveIntegerField(help_text=b'If the file is a document, the number is the document_number in RECAP docket.', null=True),
        ),
        migrations.AlterField(
            model_name='recapdocument',
            name='document_type',
            field=models.IntegerField(help_text=b'Whether this is a regular document or an attachment.', db_index=True, choices=[(1, b'PACER Document'), (2, b'Attachment'), (3, b'FDSYS Document')]),
        ),
        migrations.AlterField(
            model_name='recapdocument',
            name='filepath_ia',
            field=models.CharField(help_text=b'The URL of the file in IA', max_length=1000, null=True),
        ),
        migrations.AddField(
            model_name='caseparties',
            name='docket',
            field=models.ForeignKey(related_name='parties', to='search.Docket', help_text=b'The docket that the case party is a part of'),
        ),
    ]
