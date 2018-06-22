# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0064_add_appellate_fields'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='originatingcourtinformation',
            options={'verbose_name_plural': 'Originating Court Information'},
        ),
        migrations.RenameField(
            model_name='docket',
            old_name='originating_court',
            new_name='originating_court_information',
        ),
        migrations.AddField(
            model_name='originatingcourtinformation',
            name='docket_number',
            field=models.TextField(help_text=b'The docket number in the lower court.', blank=True),
        ),
    ]
