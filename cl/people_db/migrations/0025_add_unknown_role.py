# -*- coding: utf-8 -*-


from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('people_db', '0024_add_party_info'),
    ]

    operations = [
        migrations.AlterField(
            model_name='role',
            name='role',
            field=models.SmallIntegerField(help_text="The name of the attorney's role.", db_index=True, choices=[(1, 'Attorney to be noticed'), (2, 'Lead attorney'), (3, 'Attorney in sealed group'), (4, 'Pro hac vice'), (5, 'Self-terminated'), (6, 'Terminated'), (7, 'Suspended'), (8, 'Inactive'), (9, 'Disbarred'), (10, 'Unknown')]),
        ),
    ]
