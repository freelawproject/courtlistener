# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0014_rejigger_description_fields'),
    ]

    operations = [
        migrations.AlterField(
            model_name='docket',
            name='referred_to',
            field=models.ForeignKey(related_name='referring', blank=True, to='people_db.Person', help_text=b"The judge to whom the 'assigned_to' judge is delegated.", null=True),
        ),
    ]
