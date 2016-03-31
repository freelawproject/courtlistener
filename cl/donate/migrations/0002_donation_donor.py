# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('donate', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='donation',
            name='donor',
            field=models.ForeignKey(related_name='donations', default=1, to=settings.AUTH_USER_MODEL, help_text=b'The user that made the donation'),
            preserve_default=False,
        ),
    ]
