# Generated by Django 5.1.2 on 2024-10-18 20:18

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("alerts", "0010_pghistory_v3_4_0_trigger_update"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [
        migrations.AddField(
            model_name="scheduledalerthit",
            name="content_type",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                to="contenttypes.contenttype",
            ),
        ),
        migrations.AddField(
            model_name="scheduledalerthit",
            name="object_id",
            field=models.PositiveIntegerField(null=True),
        ),
    ]
