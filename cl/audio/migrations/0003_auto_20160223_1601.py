# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('audio', '0002_auto_20150910_1450'),
        ('people_db', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='audio',
            name='panel',
            field=models.ManyToManyField(help_text=b'The judges that heard the oral arguments', related_name='oral_argument_panel_members', to='people_db.Person', blank=True),
        ),
    ]
