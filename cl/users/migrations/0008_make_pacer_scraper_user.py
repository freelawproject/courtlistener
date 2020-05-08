# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.contrib.auth.hashers import make_password
from django.contrib.auth.management import create_permissions
from django.db import migrations, models
from django.utils import timezone
from rest_framework.authtoken.models import Token


def make_pacer_scraper_user(apps, schema_editor):
    User = apps.get_model("auth", "User",)
    UserProfile = apps.get_model("users", "UserProfile")
    Permission = apps.get_model("auth", "Permission")
    pacer_scraper = User.objects.create(
        username="pacer_scraper",
        email="pacer_scraper@free.law",
        password=make_password(None),  # Unusable password
        date_joined=timezone.now(),
    )
    profile = UserProfile.objects.create(
        user=pacer_scraper, email_confirmed=True,
    )

    # https://stackoverflow.com/a/41564061/64911
    for app_config in apps.get_app_configs():
        app_config.models_module = True
        create_permissions(app_config, verbosity=0)
        app_config.models_module = None
    Token.objects.get_or_create(user_id=pacer_scraper.id)


def delete_pacer_scraper_user(apps, schema_editor):
    User = apps.get_model("auth", "User")
    UserProfile = apps.get_model("users", "UserProfile")
    UserProfile.objects.filter(user__id__username="pacer_scraper").delete()
    User.objects.filter(username="pacer_scraper").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0007_add_is_tester_field"),
    ]

    operations = [
        migrations.RunPython(
            make_pacer_scraper_user, reverse_code=delete_pacer_scraper_user
        )
    ]
