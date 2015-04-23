# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import django.core.validators


class Migration(migrations.Migration):

    dependencies = [
        ('audio', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Favorite',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('date_modified', models.DateTimeField(db_index=True, auto_now=True, null=True)),
                ('name', models.CharField(max_length=100, verbose_name=b'a name for the alert')),
                ('notes', models.TextField(blank=True, max_length=500, verbose_name=b'notes about the favorite', validators=[django.core.validators.MaxLengthValidator(500)])),
                ('audio_id', models.ForeignKey(verbose_name=b'the audio file that is favorited', blank=True, to='audio.Audio', null=True)),
            ],
        ),
    ]
