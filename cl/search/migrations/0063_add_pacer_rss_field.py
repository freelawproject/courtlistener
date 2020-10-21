# -*- coding: utf-8 -*-


from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0062_add_indexes_to_title_section_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='court',
            name='pacer_has_rss_feed',
            field=models.NullBooleanField(help_text="Whether the court has a PACER RSS feed. If null, this doesn't apply to the given court."),
        ),
    ]
