# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0004_auto_20160325_1644'),
    ]

    operations = [
        migrations.AlterField(
            model_name='docket',
            name='assigned_to',
            field=models.ForeignKey(related_name='assigning', blank=True, to='people_db.Person', help_text=b'The judge the case was assigned to.', null=True),
        ),
        migrations.AlterField(
            model_name='docket',
            name='referred_to',
            field=models.ForeignKey(related_name='referring', blank=True, to='people_db.Person', help_text=b"The judge to whom the 'assigned_to' judge is delegated. (Not verified)", null=True),
        ),
    ]
