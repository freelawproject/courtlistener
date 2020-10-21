# -*- coding: utf-8 -*-


from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('people_db', '0038_criminal_data_fields_blankify'),
    ]

    operations = [
        migrations.AddField(
            model_name='role',
            name='role_raw',
            field=models.TextField(help_text='The raw value of the role, as a string. Items prior to 2018-06-06 may not have this value.', blank=True),
        ),
        migrations.AlterField(
            model_name='role',
            name='role',
            field=models.SmallIntegerField(help_text="The name of the attorney's role. Used primarily in district court cases.", null=True, db_index=True, choices=[(1, 'Attorney to be noticed'), (2, 'Lead attorney'), (3, 'Attorney in sealed group'), (4, 'Pro hac vice'), (5, 'Self-terminated'), (6, 'Terminated'), (7, 'Suspended'), (8, 'Inactive'), (9, 'Disbarred'), (10, 'Unknown')]),
        ),
    ]
