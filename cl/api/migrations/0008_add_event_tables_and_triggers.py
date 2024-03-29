# Generated by Django 3.2.16 on 2023-01-26 00:48

from django.conf import settings
import django.core.validators
from django.db import migrations, models
import django.db.models.deletion
import pgtrigger.compiler
import pgtrigger.migrations


class Migration(migrations.Migration):

    dependencies = [
        ('pghistory', '0005_events_middlewareevents'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('api', '0007_alter_webhook_event_type_noop'),
    ]

    operations = [
        migrations.CreateModel(
            name='WebhookHistoryEvent',
            fields=[
                ('pgh_id', models.AutoField(primary_key=True, serialize=False)),
                ('pgh_created_at', models.DateTimeField(auto_now_add=True)),
                ('pgh_label', models.TextField(help_text='The event label.')),
                ('id', models.IntegerField()),
                ('date_created', models.DateTimeField(auto_now_add=True, help_text='The moment when the item was created.')),
                ('date_modified', models.DateTimeField(auto_now=True, help_text='The last moment when the item was modified. A value in year 1750 indicates the value is unknown')),
                ('event_type', models.IntegerField(choices=[(1, 'Docket Alert'), (2, 'Search Alert'), (3, 'Recap Fetch'), (4, 'Old Docket Alerts Report')], help_text='The event type that triggers the webhook.')),
                ('url', models.URLField(help_text='The URL that receives a POST request from the webhook.', max_length=2000, validators=[django.core.validators.URLValidator(schemes=['https'])])),
                ('enabled', models.BooleanField(default=False, help_text='An on/off switch for the webhook.')),
                ('version', models.IntegerField(default=1, help_text='The specific version of the webhook provisioned.')),
                ('failure_count', models.IntegerField(default=0, help_text='The number of failures (400+ status) responses the webhook has received.')),
            ],
            options={
                'abstract': False,
            },
        ),
        pgtrigger.migrations.AddTrigger(
            model_name='webhook',
            trigger=pgtrigger.compiler.Trigger(name='snapshot_insert', sql=pgtrigger.compiler.UpsertTriggerSql(func='INSERT INTO "api_webhookhistoryevent" ("date_created", "date_modified", "enabled", "event_type", "failure_count", "id", "pgh_context_id", "pgh_created_at", "pgh_label", "pgh_obj_id", "url", "user_id", "version") VALUES (NEW."date_created", NEW."date_modified", NEW."enabled", NEW."event_type", NEW."failure_count", NEW."id", _pgh_attach_context(), NOW(), \'snapshot\', NEW."id", NEW."url", NEW."user_id", NEW."version"); RETURN NULL;', hash='d6d8359832eed68e0e3aa21cd83aa53fb32d1ff9', operation='INSERT', pgid='pgtrigger_snapshot_insert_81718', table='api_webhook', when='AFTER')),
        ),
        pgtrigger.migrations.AddTrigger(
            model_name='webhook',
            trigger=pgtrigger.compiler.Trigger(name='snapshot_update', sql=pgtrigger.compiler.UpsertTriggerSql(condition='WHEN (OLD.* IS DISTINCT FROM NEW.*)', func='INSERT INTO "api_webhookhistoryevent" ("date_created", "date_modified", "enabled", "event_type", "failure_count", "id", "pgh_context_id", "pgh_created_at", "pgh_label", "pgh_obj_id", "url", "user_id", "version") VALUES (NEW."date_created", NEW."date_modified", NEW."enabled", NEW."event_type", NEW."failure_count", NEW."id", _pgh_attach_context(), NOW(), \'snapshot\', NEW."id", NEW."url", NEW."user_id", NEW."version"); RETURN NULL;', hash='e8013d2a078cc8311e3fb1c81e247c09db921251', operation='UPDATE', pgid='pgtrigger_snapshot_update_980eb', table='api_webhook', when='AFTER')),
        ),
        migrations.AddField(
            model_name='webhookhistoryevent',
            name='pgh_context',
            field=models.ForeignKey(db_constraint=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to='pghistory.context'),
        ),
        migrations.AddField(
            model_name='webhookhistoryevent',
            name='pgh_obj',
            field=models.ForeignKey(db_constraint=False, on_delete=django.db.models.deletion.DO_NOTHING, related_name='event', to='api.webhook'),
        ),
        migrations.AddField(
            model_name='webhookhistoryevent',
            name='user',
            field=models.ForeignKey(db_constraint=False, help_text='The user that has provisioned the webhook.', on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', related_query_name='+', to=settings.AUTH_USER_MODEL),
        ),
    ]
