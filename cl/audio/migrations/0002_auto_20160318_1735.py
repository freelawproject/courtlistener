# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0001_initial'),
        ('people_db', '0001_initial'),
        ('audio', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='audio',
            name='docket',
            field=models.ForeignKey(related_name='audio_files', blank=True, to='search.Docket', help_text=b'The docket that the oral argument is a part of', null=True),
        ),
        migrations.AddField(
            model_name='audio',
            name='panel',
            field=models.ManyToManyField(help_text=b'The judges that heard the oral arguments', related_name='oral_argument_panel_members', to='people_db.Person', blank=True),
        ),
    ]
