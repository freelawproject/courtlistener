# -*- coding: utf-8 -*-


from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('people_db', '0020_person_ftm_id'),
    ]

    operations = [
        migrations.AddField(
            model_name='person',
            name='ftm_total_received',
            field=models.FloatField(help_text='The amount of money received by this person and logged by Follow the Money.', null=True, db_index=True, blank=True),
        ),
    ]
