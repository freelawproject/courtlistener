# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('scrapers', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='errorlog',
            name='court',
            field=models.ForeignKey(verbose_name=b'the court where the error occurred', to='search.Court'),
        ),
    ]
