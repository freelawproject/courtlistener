# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('judges', '0007_auto_20151230_1709'),
        ('search', '0012_auto_20160217_1220'),
    ]

    operations = [
        migrations.AddField(
            model_name='docket',
            name='referred_to',
            field=models.ForeignKey(related_name='referring', to='judges.Judge', help_text=b"The judge to whom the 'assigned_to' judge is delegated. (Not verified)", null=True),
        ),
        migrations.AlterField(
            model_name='docket',
            name='assigned_to',
            field=models.ForeignKey(related_name='assigning', to='judges.Judge', help_text=b'The judge the case was assigned to.', null=True),
        ),
        migrations.AlterField(
            model_name='docket',
            name='cause',
            field=models.CharField(help_text=b'The cause for the case.', max_length=200, null=True, blank=True),
        ),
        migrations.AlterField(
            model_name='docket',
            name='jurisdiction_type',
            field=models.CharField(help_text=b"Stands for jurisdiction in RECAP XML docket. For example, 'Diversity', 'U.S. Government Defendant'.", max_length=100, null=True, blank=True),
        ),
        migrations.AlterField(
            model_name='docket',
            name='jury_demand',
            field=models.CharField(help_text=b'The compensation demand.', max_length=500, null=True, blank=True),
        ),
        migrations.AlterField(
            model_name='docket',
            name='nature_of_suit',
            field=models.CharField(help_text=b'The nature of suit code from PACER.', max_length=100, null=True, blank=True),
        ),
        migrations.AlterField(
            model_name='recapdocument',
            name='pacer_doc_id',
            field=models.CharField(help_text=b'The ID of the document in PACER. This information is provided by RECAP.', unique=True, max_length=32),
        ),
        migrations.AlterUniqueTogether(
            name='docket',
            unique_together=set([('court', 'pacer_case_id'), ('court', 'docket_number')]),
        ),
        migrations.AlterUniqueTogether(
            name='docketentry',
            unique_together=set([('docket', 'entry_number')]),
        ),
        migrations.AlterUniqueTogether(
            name='recapdocument',
            unique_together=set([('docket_entry', 'document_number', 'attachment_number')]),
        ),
    ]
