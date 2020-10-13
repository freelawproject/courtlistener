# -*- coding: utf-8 -*-


from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0040_auto_20161102_1130'),
    ]

    operations = [
        migrations.AddField(
            model_name='opinioncluster',
            name='date_filed_is_approximate',
            field=models.BooleanField(default=False, help_text='For a variety of opinions getting the correct date filed isvery difficult. For these, we have used heuristics to approximate the date.'),
        ),
    ]
