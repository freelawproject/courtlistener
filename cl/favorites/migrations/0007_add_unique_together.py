# -*- coding: utf-8 -*-
# Generated by Django 1.11.29 on 2020-12-16 00:37
from __future__ import unicode_literals

from django.conf import settings
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('favorites', '0006_ditch_generic_fk'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='usertag',
            unique_together=set([('user', 'name')]),
        ),
    ]
