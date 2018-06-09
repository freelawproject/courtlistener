# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations
from django.utils.crypto import get_random_string


def add_tokens(apps, schema_editor):
    Alert = apps.get_model('alerts', 'Alert')
    for alert in Alert.objects.all():
        alert.secret_key = get_random_string(length=40)
        alert.save()


def remove_tokens(apps, schema_editor):
    Alert = apps.get_model('alerts', 'Alert')
    Alert.objects.all().update(secret_key='')


class Migration(migrations.Migration):

    dependencies = [
        ('alerts', '0006_add_alert_secret_key'),
    ]

    operations = [
        migrations.RunPython(add_tokens, reverse_code=remove_tokens)
    ]
