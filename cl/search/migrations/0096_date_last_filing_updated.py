# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("search", "0095_noop_update_help_text"),
    ]

    operations = [
        migrations.AddField(
            model_name="docket",
            name="date_last_filing_updated",
            field=models.DateTimeField(
                help_text=b"The time the date_last_filing field was last scraped from PACER",
                null=True,
                blank=True,
            ),
        ),
    ]
