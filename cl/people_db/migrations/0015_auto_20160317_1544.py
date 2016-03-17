# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('people_db', '0014_merge'),
    ]

    operations = [
        migrations.AlterField(
            model_name='race',
            name='race',
            field=models.CharField(unique=True, max_length=5, choices=[(b'w', b'White'), (b'b', b'Black or African American'), (b'i', b'American Indian or Alaska Native'), (b'a', b'Asian'), (b'p', b'Native Hawaiian or Other Pacific Islander'), (b'h', b'Hispanic/Latino')]),
        ),
    ]
