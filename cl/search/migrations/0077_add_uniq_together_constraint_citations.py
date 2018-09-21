# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0076_remove_legacy_citation_field'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='citation',
            unique_together=set([('cluster', 'volume', 'reporter', 'page')]),
        ),
    ]
