# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('people_db', '0012_create_vote_percent_fields_simplify_aba_dates'),
    ]

    operations = [
        migrations.AlterField(
            model_name='position',
            name='appointer',
            field=models.ForeignKey(related_name='appointed_positions', blank=True, to='people_db.Position', help_text=b'If this is an appointed position, the person-position responsible for the appointing.', null=True),
        ),
    ]
