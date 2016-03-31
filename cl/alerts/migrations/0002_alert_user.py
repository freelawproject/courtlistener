# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('alerts', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='alert',
            name='user',
            field=models.ForeignKey(related_name='alerts', default=1, to=settings.AUTH_USER_MODEL, help_text=b'The user that created the item'),
            preserve_default=False,
        ),
    ]
