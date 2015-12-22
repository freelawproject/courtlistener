# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0010_auto_20151214_1142'),
    ]

    operations = [
        migrations.AlterField(
            model_name='docket',
            name='court',
            field=models.ForeignKey(related_name='dockets', to='search.Court', help_text=b'The court where the docket was filed'),
        ),
    ]
