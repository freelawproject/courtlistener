# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0008_auto_20151117_1526'),
    ]

    operations = [
        migrations.AlterField(
            model_name='docket',
            name='slug',
            field=models.SlugField(help_text=b'URL that the document should map to (the slug)', max_length=75, null=True, db_index=False),
        ),
        migrations.AlterField(
            model_name='opinioncluster',
            name='slug',
            field=models.SlugField(help_text=b'URL that the document should map to (the slug)', max_length=75, null=True, db_index=False),
        ),
    ]
