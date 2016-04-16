# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('people_db', '0014_auto_20160415_1116'),
    ]

    operations = [
        migrations.AlterField(
            model_name='politicalaffiliation',
            name='political_party',
            field=models.CharField(max_length=5, choices=[(b'd', b'Democrat'), (b'r', b'Republican'), (b'i', b'Independent'), (b'g', b'Green'), (b'l', b'Libertarian'), (b'f', b'Federalist'), (b'w', b'Whig'), (b'j', b'Jeffersonian Republican'), (b'u', b'National Union')]),
        ),
    ]
