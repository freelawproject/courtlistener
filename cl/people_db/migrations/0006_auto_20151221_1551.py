# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('judges', '0005_auto_20151215_1502'),
    ]

    operations = [
        migrations.AlterField(
            model_name='education',
            name='school',
            field=models.ForeignKey(related_name='educations', to='judges.School'),
        ),
    ]
