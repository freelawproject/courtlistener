# -*- coding: utf-8 -*-


import sys

from django.db import migrations

from cl.lib.migration_utils import load_migration_fixture, make_new_user


def load_fixture(apps, schema_editor):
    if 'test' not in sys.argv:
        fixture = 'bar_membership_data'
        load_migration_fixture(apps, schema_editor, fixture, 'users')

    # Add tenn user group permissions
    Group = apps.get_model("auth", "Group",)
    Group.objects.create(name="tenn_work_uploaders",)

    # Make users
    make_new_user(
        apps,
        schema_editor,
        "recap",
        "recap@free.law",
        ["has_recap_upload_access"],
    )
    make_new_user(
        apps,
        schema_editor,
        "recap-email",
        "recap-email@free.law",
        ["has_recap_upload_access"],
    )


def unload_fixture(apps, schema_editor):
    """Delete everything"""
    BarMembershipModel = apps.get_model("users", "BarMembership")
    BarMembershipModel.objects.all().delete()

    # Remove tenn user group permissions
    Group = apps.get_model("auth", "Group")
    Group.objects.filter(name="tenn_work_uploaders").delete()

    # Remove custom users
    User = apps.get_model("auth", "User")
    UserProfile = apps.get_model("users", "UserProfile")
    UserProfile.objects.filter(user__id__username="recap").delete()
    User.objects.filter(username="recap").delete()
    User.objects.filter(username="recap-email").delete()


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(load_fixture, reverse_code=unload_fixture),
    ]

