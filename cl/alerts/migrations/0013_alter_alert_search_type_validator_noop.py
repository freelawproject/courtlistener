# Generated by Django 5.1.2 on 2024-12-04 23:12

import cl.alerts.models
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("alerts", "0012_add_schedule_alert_hit_content_type_index"),
    ]

    operations = [
        migrations.AlterField(
            model_name="alert",
            name="alert_type",
            field=models.CharField(
                choices=[
                    ("o", "Opinions"),
                    ("r", "RECAP"),
                    ("oa", "Oral Arguments"),
                ],
                help_text="The type of search alert this is, one of: o (Opinions), r (RECAP), oa (Oral Arguments)",
                max_length=3,
                validators=[cl.alerts.models.validate_alert_type],
            ),
        ),
        migrations.AlterField(
            model_name="alertevent",
            name="alert_type",
            field=models.CharField(
                choices=[
                    ("o", "Opinions"),
                    ("r", "RECAP"),
                    ("oa", "Oral Arguments"),
                ],
                help_text="The type of search alert this is, one of: o (Opinions), r (RECAP), oa (Oral Arguments)",
                max_length=3,
                validators=[cl.alerts.models.validate_alert_type],
            ),
        ),
    ]