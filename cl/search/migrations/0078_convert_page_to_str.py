# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0077_add_uniq_together_constraint_citations'),
    ]

    operations = [
        migrations.AlterField(
            model_name='citation',
            name='page',
            field=models.TextField(help_text=b"The 'page' of the citation in the reporter. Unfortunately, this is not an integer, but is a string-type because several jurisdictions do funny things with the so-called 'page'. For example, we have seen Roman numerals in Nebraska, 13301-M in Connecticut, and 144M in Montana."),
        ),
    ]
