# Generated by Django 3.2.18 on 2023-04-04 15:11

from django.db import migrations, models
import pgtrigger.compiler
import pgtrigger.migrations


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0010_add_event_tables_and_triggers'),
    ]

    operations = [
        pgtrigger.migrations.RemoveTrigger(
            model_name='userprofile',
            name='snapshot_insert',
        ),
        pgtrigger.migrations.RemoveTrigger(
            model_name='userprofile',
            name='snapshot_update',
        ),
        migrations.AddField(
            model_name='userprofile',
            name='docket_default_order_desc',
            field=models.BooleanField(default=False, help_text='Sort dockets in descending order by default'),
        ),
        migrations.AddField(
            model_name='userprofileevent',
            name='docket_default_order_desc',
            field=models.BooleanField(default=False, help_text='Sort dockets in descending order by default'),
        ),
        pgtrigger.migrations.AddTrigger(
            model_name='userprofile',
            trigger=pgtrigger.compiler.Trigger(name='snapshot_insert', sql=pgtrigger.compiler.UpsertTriggerSql(func='INSERT INTO "users_userprofileevent" ("activation_key", "address1", "address2", "auto_subscribe", "avatar", "city", "docket_default_order_desc", "email_confirmed", "employer", "id", "is_tester", "key_expires", "notes", "pgh_context_id", "pgh_created_at", "pgh_label", "pgh_obj_id", "plaintext_preferred", "recap_email", "state", "stub_account", "unlimited_docket_alerts", "user_id", "wants_newsletter", "zip_code") VALUES (NEW."activation_key", NEW."address1", NEW."address2", NEW."auto_subscribe", NEW."avatar", NEW."city", NEW."docket_default_order_desc", NEW."email_confirmed", NEW."employer", NEW."id", NEW."is_tester", NEW."key_expires", NEW."notes", _pgh_attach_context(), NOW(), \'snapshot\', NEW."id", NEW."plaintext_preferred", NEW."recap_email", NEW."state", NEW."stub_account", NEW."unlimited_docket_alerts", NEW."user_id", NEW."wants_newsletter", NEW."zip_code"); RETURN NULL;', hash='2199693910e840c406dd5edb72796bca1a60fffd', operation='INSERT', pgid='pgtrigger_snapshot_insert_31610', table='users_userprofile', when='AFTER')),
        ),
        pgtrigger.migrations.AddTrigger(
            model_name='userprofile',
            trigger=pgtrigger.compiler.Trigger(name='snapshot_update', sql=pgtrigger.compiler.UpsertTriggerSql(condition='WHEN (OLD.* IS DISTINCT FROM NEW.*)', func='INSERT INTO "users_userprofileevent" ("activation_key", "address1", "address2", "auto_subscribe", "avatar", "city", "docket_default_order_desc", "email_confirmed", "employer", "id", "is_tester", "key_expires", "notes", "pgh_context_id", "pgh_created_at", "pgh_label", "pgh_obj_id", "plaintext_preferred", "recap_email", "state", "stub_account", "unlimited_docket_alerts", "user_id", "wants_newsletter", "zip_code") VALUES (NEW."activation_key", NEW."address1", NEW."address2", NEW."auto_subscribe", NEW."avatar", NEW."city", NEW."docket_default_order_desc", NEW."email_confirmed", NEW."employer", NEW."id", NEW."is_tester", NEW."key_expires", NEW."notes", _pgh_attach_context(), NOW(), \'snapshot\', NEW."id", NEW."plaintext_preferred", NEW."recap_email", NEW."state", NEW."stub_account", NEW."unlimited_docket_alerts", NEW."user_id", NEW."wants_newsletter", NEW."zip_code"); RETURN NULL;', hash='79bb81397f216ff67c082a92d7ecce765a6d209d', operation='UPDATE', pgid='pgtrigger_snapshot_update_74231', table='users_userprofile', when='AFTER')),
        ),
    ]
