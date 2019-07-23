# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('search', '0063_add_pacer_rss_field'),
        ('alerts', '0007_populate_alert_secret_key'),
    ]

    operations = [
        migrations.CreateModel(
            name='DocketAlert',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('date_created', models.DateTimeField(help_text=b'The time when this item was created', auto_now_add=True, db_index=True)),
                ('secret_key', models.CharField(max_length=40, verbose_name=b'A key to be used in links to access the alert without having to log in. Can be used for a variety of purposes.')),
                ('docket', models.ForeignKey(related_name='alerts', to='search.Docket', help_text=b'The docket that we are subscribed to.', on_delete=models.CASCADE)),
                ('user', models.ForeignKey(related_name='docket_alerts', to=settings.AUTH_USER_MODEL, help_text=b'The user that is subscribed to the docket.',
                                           on_delete=models.CASCADE)),
            ],
        ),
        migrations.AlterUniqueTogether(
            name='docketalert',
            unique_together=set([('docket', 'user')]),
        ),
    ]
