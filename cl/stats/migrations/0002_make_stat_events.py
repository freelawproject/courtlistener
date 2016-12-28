# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('stats', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Event',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('date_created', models.DateTimeField(help_text=b'The moment when the event was logged', auto_now_add=True)),
                ('description', models.CharField(help_text=b'A human-readable description of the event', max_length=200)),
            ],
        ),
    ]
