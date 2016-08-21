# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0035_auto_20160821_1029'),
    ]

    operations = [
        migrations.AlterField(
            model_name='docket',
            name='cause',
            field=models.CharField(help_text=b'The cause for the case.', max_length=2000, blank=True),
        ),
    ]
