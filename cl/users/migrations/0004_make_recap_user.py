# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.contrib.auth.hashers import make_password
from django.contrib.auth.management import create_permissions
from django.db import migrations, models
from django.utils import timezone
from rest_framework.authtoken.models import Token


def make_recap_user(apps, schema_editor):
    User = apps.get_model('auth', 'User',)
    UserProfile = apps.get_model('users', 'UserProfile')
    Permission = apps.get_model('auth', 'Permission')
    recap_user = User.objects.create(
        username='recap',
        email='recap@free.law',
        password=make_password(None),  # Unusable password
        date_joined=timezone.now(),
    )
    profile = UserProfile.objects.create(
        user=recap_user,
        email_confirmed=True,
    )

    # https://stackoverflow.com/a/41564061/64911
    for app_config in apps.get_app_configs():
        app_config.models_module = True
        create_permissions(app_config, verbosity=0)
        app_config.models_module = None

    p = Permission.objects.get(codename='has_recap_upload_access')
    recap_user.user_permissions.add(p)
    Token.objects.get_or_create(user_id=recap_user.id)


def delete_recap_user(apps, schema_editor):
    User = apps.get_model('auth', 'User')
    UserProfile = apps.get_model('users', 'UserProfile')
    UserProfile.objects.filter(user__id__username='recap').delete()
    User.objects.filter(username='recap').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0003_add_auth_tokens'),
    ]

    operations = [
        migrations.RunPython(make_recap_user, reverse_code=delete_recap_user)
    ]
