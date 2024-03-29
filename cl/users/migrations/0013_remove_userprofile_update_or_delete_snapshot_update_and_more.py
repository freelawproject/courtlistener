# Generated by Django 5.0 on 2023-12-19 13:34

import pgtrigger.compiler
import pgtrigger.migrations
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0012_update_triggers"),
    ]

    operations = [
        pgtrigger.migrations.RemoveTrigger(
            model_name="userprofile",
            name="update_or_delete_snapshot_update",
        ),
        pgtrigger.migrations.RemoveTrigger(
            model_name="userprofile",
            name="update_or_delete_snapshot_delete",
        ),
        migrations.AddField(
            model_name="userprofile",
            name="neon_account_id",
            field=models.CharField(
                blank=True,
                help_text="Unique identifier assigned by Neon CRM to a customer record",
            ),
        ),
        migrations.AddField(
            model_name="userprofileevent",
            name="neon_account_id",
            field=models.CharField(
                blank=True,
                help_text="Unique identifier assigned by Neon CRM to a customer record",
            ),
        ),
        pgtrigger.migrations.AddTrigger(
            model_name="userprofile",
            trigger=pgtrigger.compiler.Trigger(
                name="update_or_delete_snapshot_update",
                sql=pgtrigger.compiler.UpsertTriggerSql(
                    condition="WHEN (OLD.* IS DISTINCT FROM NEW.*)",
                    func='INSERT INTO "users_userprofileevent" ("activation_key", "address1", "address2", "auto_subscribe", "avatar", "city", "docket_default_order_desc", "email_confirmed", "employer", "id", "is_tester", "key_expires", "neon_account_id", "notes", "pgh_context_id", "pgh_created_at", "pgh_label", "pgh_obj_id", "plaintext_preferred", "recap_email", "state", "stub_account", "unlimited_docket_alerts", "user_id", "wants_newsletter", "zip_code") VALUES (OLD."activation_key", OLD."address1", OLD."address2", OLD."auto_subscribe", OLD."avatar", OLD."city", OLD."docket_default_order_desc", OLD."email_confirmed", OLD."employer", OLD."id", OLD."is_tester", OLD."key_expires", OLD."neon_account_id", OLD."notes", _pgh_attach_context(), NOW(), \'update_or_delete_snapshot\', OLD."id", OLD."plaintext_preferred", OLD."recap_email", OLD."state", OLD."stub_account", OLD."unlimited_docket_alerts", OLD."user_id", OLD."wants_newsletter", OLD."zip_code"); RETURN NULL;',
                    hash="1cc203ac382ca8e8508dada33ea70e2a9c207986",
                    operation="UPDATE",
                    pgid="pgtrigger_update_or_delete_snapshot_update_c9b7b",
                    table="users_userprofile",
                    when="AFTER",
                ),
            ),
        ),
        pgtrigger.migrations.AddTrigger(
            model_name="userprofile",
            trigger=pgtrigger.compiler.Trigger(
                name="update_or_delete_snapshot_delete",
                sql=pgtrigger.compiler.UpsertTriggerSql(
                    func='INSERT INTO "users_userprofileevent" ("activation_key", "address1", "address2", "auto_subscribe", "avatar", "city", "docket_default_order_desc", "email_confirmed", "employer", "id", "is_tester", "key_expires", "neon_account_id", "notes", "pgh_context_id", "pgh_created_at", "pgh_label", "pgh_obj_id", "plaintext_preferred", "recap_email", "state", "stub_account", "unlimited_docket_alerts", "user_id", "wants_newsletter", "zip_code") VALUES (OLD."activation_key", OLD."address1", OLD."address2", OLD."auto_subscribe", OLD."avatar", OLD."city", OLD."docket_default_order_desc", OLD."email_confirmed", OLD."employer", OLD."id", OLD."is_tester", OLD."key_expires", OLD."neon_account_id", OLD."notes", _pgh_attach_context(), NOW(), \'update_or_delete_snapshot\', OLD."id", OLD."plaintext_preferred", OLD."recap_email", OLD."state", OLD."stub_account", OLD."unlimited_docket_alerts", OLD."user_id", OLD."wants_newsletter", OLD."zip_code"); RETURN NULL;',
                    hash="c56d9c110e9ffaae378b700bcb8c086d663782b7",
                    operation="DELETE",
                    pgid="pgtrigger_update_or_delete_snapshot_delete_f463b",
                    table="users_userprofile",
                    when="AFTER",
                ),
            ),
        ),
    ]
