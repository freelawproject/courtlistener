# In prod, this migration should be faked. The SQL does nothing. In dev, it
# doesn't matter what you do, since it does nothing.

# -*- coding: utf-8 -*-
# Generated by Django 1.11.29 on 2021-01-14 17:59
from __future__ import unicode_literals

import localflavor.us.models
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('people_db', '0047_remove_disclosures'),
    ]

    operations = [
        migrations.AlterField(
            model_name='attorney',
            name='email',
            field=models.EmailField(blank=True, help_text='The email address of the attorney.', max_length=254),
        ),
        migrations.AlterField(
            model_name='attorney',
            name='fax',
            field=localflavor.us.models.PhoneNumberField(blank=True, help_text='The fax number of the attorney.', max_length=20),
        ),
        migrations.AlterField(
            model_name='attorney',
            name='phone',
            field=localflavor.us.models.PhoneNumberField(blank=True, help_text='The phone number of the attorney.', max_length=20),
        ),
    ]
