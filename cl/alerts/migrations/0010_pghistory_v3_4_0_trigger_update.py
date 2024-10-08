# Generated by Django 5.0.8 on 2024-09-10 16:53

import django.db.models.deletion
import pgtrigger.compiler
import pgtrigger.migrations
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("alerts", "0009_alter_alert_search_types_noop"),
    ]

    operations = [
        pgtrigger.migrations.RemoveTrigger(
            model_name="alert",
            name="update_or_delete_snapshot_update",
        ),
        pgtrigger.migrations.RemoveTrigger(
            model_name="alert",
            name="update_or_delete_snapshot_delete",
        ),
        pgtrigger.migrations.RemoveTrigger(
            model_name="docketalert",
            name="update_or_delete_snapshot_delete",
        ),
        pgtrigger.migrations.RemoveTrigger(
            model_name="docketalert",
            name="update_or_delete_snapshot_update",
        ),
        migrations.AlterField(
            model_name="alertevent",
            name="pgh_obj",
            field=models.ForeignKey(
                db_constraint=False,
                on_delete=django.db.models.deletion.DO_NOTHING,
                related_name="events",
                to="alerts.alert",
            ),
        ),
        migrations.AlterField(
            model_name="docketalertevent",
            name="pgh_obj",
            field=models.ForeignKey(
                db_constraint=False,
                on_delete=django.db.models.deletion.DO_NOTHING,
                related_name="events",
                to="alerts.docketalert",
            ),
        ),
        pgtrigger.migrations.AddTrigger(
            model_name="alert",
            trigger=pgtrigger.compiler.Trigger(
                name="update_update",
                sql=pgtrigger.compiler.UpsertTriggerSql(
                    condition='WHEN (OLD."alert_type" IS DISTINCT FROM (NEW."alert_type") OR OLD."date_last_hit" IS DISTINCT FROM (NEW."date_last_hit") OR OLD."id" IS DISTINCT FROM (NEW."id") OR OLD."name" IS DISTINCT FROM (NEW."name") OR OLD."query" IS DISTINCT FROM (NEW."query") OR OLD."rate" IS DISTINCT FROM (NEW."rate") OR OLD."secret_key" IS DISTINCT FROM (NEW."secret_key") OR OLD."user_id" IS DISTINCT FROM (NEW."user_id"))',
                    func='INSERT INTO "alerts_alertevent" ("alert_type", "date_created", "date_last_hit", "date_modified", "id", "name", "pgh_context_id", "pgh_created_at", "pgh_label", "pgh_obj_id", "query", "rate", "secret_key", "user_id") VALUES (OLD."alert_type", OLD."date_created", OLD."date_last_hit", OLD."date_modified", OLD."id", OLD."name", _pgh_attach_context(), NOW(), \'update\', OLD."id", OLD."query", OLD."rate", OLD."secret_key", OLD."user_id"); RETURN NULL;',
                    hash="d10c466ad18caf5d1aeea5985af5c6e6e14e17d3",
                    operation="UPDATE",
                    pgid="pgtrigger_update_update_953db",
                    table="alerts_alert",
                    when="AFTER",
                ),
            ),
        ),
        pgtrigger.migrations.AddTrigger(
            model_name="alert",
            trigger=pgtrigger.compiler.Trigger(
                name="delete_delete",
                sql=pgtrigger.compiler.UpsertTriggerSql(
                    func='INSERT INTO "alerts_alertevent" ("alert_type", "date_created", "date_last_hit", "date_modified", "id", "name", "pgh_context_id", "pgh_created_at", "pgh_label", "pgh_obj_id", "query", "rate", "secret_key", "user_id") VALUES (OLD."alert_type", OLD."date_created", OLD."date_last_hit", OLD."date_modified", OLD."id", OLD."name", _pgh_attach_context(), NOW(), \'delete\', OLD."id", OLD."query", OLD."rate", OLD."secret_key", OLD."user_id"); RETURN NULL;',
                    hash="7c45dc1ce256430854bb607919cb01032db5ff5a",
                    operation="DELETE",
                    pgid="pgtrigger_delete_delete_2fa4e",
                    table="alerts_alert",
                    when="AFTER",
                ),
            ),
        ),
        pgtrigger.migrations.AddTrigger(
            model_name="docketalert",
            trigger=pgtrigger.compiler.Trigger(
                name="update_update",
                sql=pgtrigger.compiler.UpsertTriggerSql(
                    condition='WHEN (OLD."alert_type" IS DISTINCT FROM (NEW."alert_type") OR OLD."date_last_hit" IS DISTINCT FROM (NEW."date_last_hit") OR OLD."docket_id" IS DISTINCT FROM (NEW."docket_id") OR OLD."id" IS DISTINCT FROM (NEW."id") OR OLD."secret_key" IS DISTINCT FROM (NEW."secret_key") OR OLD."user_id" IS DISTINCT FROM (NEW."user_id"))',
                    func='INSERT INTO "alerts_docketalertevent" ("alert_type", "date_created", "date_last_hit", "date_modified", "docket_id", "id", "pgh_context_id", "pgh_created_at", "pgh_label", "pgh_obj_id", "secret_key", "user_id") VALUES (OLD."alert_type", OLD."date_created", OLD."date_last_hit", OLD."date_modified", OLD."docket_id", OLD."id", _pgh_attach_context(), NOW(), \'update\', OLD."id", OLD."secret_key", OLD."user_id"); RETURN NULL;',
                    hash="cf12ed58779f12bde3fd0bdaec1ac03cbc487dd3",
                    operation="UPDATE",
                    pgid="pgtrigger_update_update_5b7b3",
                    table="alerts_docketalert",
                    when="AFTER",
                ),
            ),
        ),
        pgtrigger.migrations.AddTrigger(
            model_name="docketalert",
            trigger=pgtrigger.compiler.Trigger(
                name="delete_delete",
                sql=pgtrigger.compiler.UpsertTriggerSql(
                    func='INSERT INTO "alerts_docketalertevent" ("alert_type", "date_created", "date_last_hit", "date_modified", "docket_id", "id", "pgh_context_id", "pgh_created_at", "pgh_label", "pgh_obj_id", "secret_key", "user_id") VALUES (OLD."alert_type", OLD."date_created", OLD."date_last_hit", OLD."date_modified", OLD."docket_id", OLD."id", _pgh_attach_context(), NOW(), \'delete\', OLD."id", OLD."secret_key", OLD."user_id"); RETURN NULL;',
                    hash="1ba35d31c8ea4a81ea2c41a1dcb4f57ad89b329e",
                    operation="DELETE",
                    pgid="pgtrigger_delete_delete_5ad6b",
                    table="alerts_docketalert",
                    when="AFTER",
                ),
            ),
        ),
    ]
