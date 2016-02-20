# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('favorites', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='favorite',
            name='date_created',
            field=models.DateTimeField(help_text=b'The original creation date for the item', auto_now_add=True, db_index=True),
        ),
    ]
