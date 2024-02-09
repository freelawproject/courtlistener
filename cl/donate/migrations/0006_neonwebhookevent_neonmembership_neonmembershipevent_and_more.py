# Generated by Django 5.0 on 2023-12-20 23:18

import django.core.serializers.json
import django.db.models.deletion
import pgtrigger.compiler
import pgtrigger.migrations
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        (
            "donate",
            "0005_remove_donation_update_or_delete_snapshot_update_and_more",
        ),
        ("pghistory", "0005_events_middlewareevents"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="NeonWebhookEvent",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "date_created",
                    models.DateTimeField(
                        auto_now_add=True,
                        db_index=True,
                        help_text="The moment when the item was created.",
                    ),
                ),
                (
                    "date_modified",
                    models.DateTimeField(
                        auto_now=True,
                        db_index=True,
                        help_text="The last moment when the item was modified. A value in year 1750 indicates the value is unknown",
                    ),
                ),
                (
                    "trigger",
                    models.PositiveSmallIntegerField(
                        choices=[
                            (1, "createMembership"),
                            (2, "editMembership"),
                            (3, "deleteMembership"),
                            (4, "updateMembership"),
                        ],
                        help_text="Specifies the action that initiated this webhook event",
                    ),
                ),
                (
                    "account_id",
                    models.CharField(
                        blank=True,
                        help_text="Unique identifier assigned by Neon CRM to a customer record",
                    ),
                ),
                (
                    "membership_id",
                    models.CharField(
                        blank=True,
                        help_text="Unique identifier assigned by Neon CRM to a membership record",
                    ),
                ),
                (
                    "content",
                    models.JSONField(
                        encoder=django.core.serializers.json.DjangoJSONEncoder,
                        help_text="The content of the payload of the POST request.",
                    ),
                ),
            ],
            options={
                "abstract": False,
            },
        ),
        migrations.CreateModel(
            name="NeonMembership",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "date_created",
                    models.DateTimeField(
                        auto_now_add=True,
                        db_index=True,
                        help_text="The moment when the item was created.",
                    ),
                ),
                (
                    "date_modified",
                    models.DateTimeField(
                        auto_now=True,
                        db_index=True,
                        help_text="The last moment when the item was modified. A value in year 1750 indicates the value is unknown",
                    ),
                ),
                (
                    "neon_id",
                    models.CharField(
                        blank=True,
                        help_text="Unique identifier assigned by Neon CRM to a membership record",
                    ),
                ),
                (
                    "level",
                    models.PositiveSmallIntegerField(
                        choices=[
                            (1, "CL Membership - Basic"),
                            (2, "CL Legacy Membership"),
                            (3, "CL Membership - Tier 1"),
                            (4, "CL Membership - Tier 2"),
                            (5, "CL Membership - Tier 3"),
                            (6, "CL Membership - Tier 4"),
                            (7, "CL Membership - Tier 5"),
                            (8, "CL Platinum Membership"),
                        ],
                        help_text="The current membership tier of a user within Neon CRM",
                    ),
                ),
                (
                    "termination_date",
                    models.DateTimeField(
                        blank=True,
                        help_text="The date a user's Neon membership will be terminated",
                        null=True,
                    ),
                ),
                (
                    "user",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="membership",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="the user linked to the membership",
                    ),
                ),
            ],
            options={
                "abstract": False,
            },
        ),
        migrations.CreateModel(
            name="NeonMembershipEvent",
            fields=[
                (
                    "pgh_id",
                    models.AutoField(primary_key=True, serialize=False),
                ),
                ("pgh_created_at", models.DateTimeField(auto_now_add=True)),
                ("pgh_label", models.TextField(help_text="The event label.")),
                ("id", models.IntegerField()),
                (
                    "date_created",
                    models.DateTimeField(
                        auto_now_add=True,
                        help_text="The moment when the item was created.",
                    ),
                ),
                (
                    "date_modified",
                    models.DateTimeField(
                        auto_now=True,
                        help_text="The last moment when the item was modified. A value in year 1750 indicates the value is unknown",
                    ),
                ),
                (
                    "neon_id",
                    models.CharField(
                        blank=True,
                        help_text="Unique identifier assigned by Neon CRM to a membership record",
                    ),
                ),
                (
                    "level",
                    models.PositiveSmallIntegerField(
                        choices=[
                            (1, "CL Membership - Basic"),
                            (2, "CL Legacy Membership"),
                            (3, "CL Membership - Tier 1"),
                            (4, "CL Membership - Tier 2"),
                            (5, "CL Membership - Tier 3"),
                            (6, "CL Membership - Tier 4"),
                            (7, "CL Membership - Tier 5"),
                            (8, "CL Platinum Membership"),
                        ],
                        help_text="The current membership tier of a user within Neon CRM",
                    ),
                ),
                (
                    "termination_date",
                    models.DateTimeField(
                        blank=True,
                        help_text="The date a user's Neon membership will be terminated",
                        null=True,
                    ),
                ),
                (
                    "pgh_context",
                    models.ForeignKey(
                        db_constraint=False,
                        null=True,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        related_name="+",
                        to="pghistory.context",
                    ),
                ),
                (
                    "pgh_obj",
                    models.ForeignKey(
                        db_constraint=False,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        related_name="event",
                        to="donate.neonmembership",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        db_constraint=False,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        related_name="+",
                        related_query_name="+",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="the user linked to the membership",
                    ),
                ),
            ],
            options={
                "abstract": False,
            },
        ),
        pgtrigger.migrations.AddTrigger(
            model_name="neonmembership",
            trigger=pgtrigger.compiler.Trigger(
                name="update_or_delete_snapshot_update",
                sql=pgtrigger.compiler.UpsertTriggerSql(
                    condition='WHEN (OLD."id" IS DISTINCT FROM (NEW."id") OR OLD."date_created" IS DISTINCT FROM (NEW."date_created") OR OLD."user_id" IS DISTINCT FROM (NEW."user_id") OR OLD."neon_id" IS DISTINCT FROM (NEW."neon_id") OR OLD."level" IS DISTINCT FROM (NEW."level") OR OLD."termination_date" IS DISTINCT FROM (NEW."termination_date"))',
                    func='INSERT INTO "donate_neonmembershipevent" ("date_created", "date_modified", "id", "level", "neon_id", "pgh_context_id", "pgh_created_at", "pgh_label", "pgh_obj_id", "termination_date", "user_id") VALUES (OLD."date_created", OLD."date_modified", OLD."id", OLD."level", OLD."neon_id", _pgh_attach_context(), NOW(), \'update_or_delete_snapshot\', OLD."id", OLD."termination_date", OLD."user_id"); RETURN NULL;',
                    hash="271ab11c535ea945d8645eda1cd161924f5e6eaa",
                    operation="UPDATE",
                    pgid="pgtrigger_update_or_delete_snapshot_update_91de0",
                    table="donate_neonmembership",
                    when="AFTER",
                ),
            ),
        ),
        pgtrigger.migrations.AddTrigger(
            model_name="neonmembership",
            trigger=pgtrigger.compiler.Trigger(
                name="update_or_delete_snapshot_delete",
                sql=pgtrigger.compiler.UpsertTriggerSql(
                    func='INSERT INTO "donate_neonmembershipevent" ("date_created", "date_modified", "id", "level", "neon_id", "pgh_context_id", "pgh_created_at", "pgh_label", "pgh_obj_id", "termination_date", "user_id") VALUES (OLD."date_created", OLD."date_modified", OLD."id", OLD."level", OLD."neon_id", _pgh_attach_context(), NOW(), \'update_or_delete_snapshot\', OLD."id", OLD."termination_date", OLD."user_id"); RETURN NULL;',
                    hash="497714fb076872b92e16fc293c94c874b0ff431d",
                    operation="DELETE",
                    pgid="pgtrigger_update_or_delete_snapshot_delete_e81b6",
                    table="donate_neonmembership",
                    when="AFTER",
                ),
            ),
        ),
    ]
