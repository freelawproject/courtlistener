# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0009_opinioncluster_case_name_short'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='opinionscited',
            options={'verbose_name_plural': 'Opinions cited'},
        ),
        migrations.AlterField(
            model_name='opinion',
            name='html_columbia',
            field=models.TextField(help_text=b'HTML of Columbia archive', null=True, blank=True),
        ),
        migrations.AlterField(
            model_name='opinioncluster',
            name='posture',
            field=models.TextField(help_text=b'The procedural posture of the case.', blank=True),
        ),
    ]
