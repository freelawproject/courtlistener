# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('stats', '0002_make_stat_events'),
    ]

    operations = [
        migrations.AddField(
            model_name='event',
            name='user',
            field=models.ForeignKey(related_name='events', blank=True, to=settings.AUTH_USER_MODEL, help_text=b'A user associated with the event.', null=True,
                                    on_delete=models.CASCADE),
        ),
    ]
