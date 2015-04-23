# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0006_auto_20150803_1511'),
    ]

    operations = [
        migrations.AlterField(
            model_name='opinioncluster',
            name='docket',
            field=models.ForeignKey(related_name='clusters', default=1, to='search.Docket', help_text=b'The docket that the opinion cluster is a part of'),
            preserve_default=False,
        ),
    ]
