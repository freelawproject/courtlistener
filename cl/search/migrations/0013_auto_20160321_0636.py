# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0012_auto_20160217_1220'),
    ]

    operations = [
        migrations.CreateModel(
            name='CaseParties',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('first_name', models.CharField(help_text=b'First name', max_length=500, blank=True)),
                ('last_name', models.CharField(help_text=b'Last name', max_length=500, blank=True)),
                ('middle_name', models.CharField(help_text=b'Middle name', max_length=500, blank=True)),
                ('suffix_name', models.CharField(help_text=b'Suffix name', max_length=500, blank=True)),
                ('role', models.CharField(help_text=b'Parties role in the case', max_length=500, blank=True)),
            ],
        ),
        migrations.AddField(
            model_name='docket',
            name='fdsys_case_id',
            field=models.CharField(help_text=b'The cased ID provided by FDSYS.', max_length=100, null=True, db_index=True, blank=True),
        ),
        migrations.AddField(
            model_name='caseparties',
            name='docket',
            field=models.ForeignKey(related_name='parties', to='search.Docket', help_text=b'The docket that the case party is a part of'),
        ),
    ]
