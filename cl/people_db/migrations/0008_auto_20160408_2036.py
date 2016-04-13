# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('people_db', '0007_auto_20160408_1109'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='abarating',
            options={'verbose_name': 'American Bar Association Rating', 'verbose_name_plural': 'American Bar Association Ratings'},
        ),
        migrations.AddField(
            model_name='person',
            name='has_photo',
            field=models.BooleanField(default=False, help_text=b'Whether there is a photo corresponding to this person in the judge pics project.'),
        ),
    ]
