# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0066_add_og_ordering_judge_rename_judgement_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='recapdocument',
            name='file_size',
            field=models.IntegerField(help_text=b'The size of the file in bytes, if known', null=True, blank=True),
        ),
        migrations.AlterField(
            model_name='docket',
            name='appeal_from_str',
            field=models.TextField(help_text=b'In appellate cases, this is the lower court or administrative body where this case was originally heard. This field is frequently blank due to it not being populated historically. This field may have values when the appeal_from field does not. That can happen if we are unable to normalize the value in this field.', blank=True),
        ),
        migrations.AlterField(
            model_name='originatingcourtinformation',
            name='date_judgment',
            field=models.DateField(help_text=b'The date of the order or judgment in the lower court.', null=True, blank=True),
        ),
        migrations.AlterField(
            model_name='originatingcourtinformation',
            name='date_judgment_eod',
            field=models.DateField(help_text=b'The date the judgment was Entered On the Docket at the lower court.', null=True, blank=True),
        ),
    ]
