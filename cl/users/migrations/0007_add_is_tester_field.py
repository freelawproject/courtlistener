# -*- coding: utf-8 -*-


from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0006_add_unlimited_alert_field'),
    ]

    operations = [
        migrations.AddField(
            model_name='userprofile',
            name='is_tester',
            field=models.BooleanField(default=False, help_text='The user tests new features before they are finished'),
        ),
    ]
