# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Donation',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('date_modified', models.DateTimeField(auto_now=True, db_index=True)),
                ('date_created', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('clearing_date', models.DateTimeField(null=True, blank=True)),
                ('send_annual_reminder', models.BooleanField(default=False, verbose_name=b'Send me a reminder to donate again in one year')),
                ('amount', models.DecimalField(default=None, max_digits=10, decimal_places=2)),
                ('payment_provider', models.CharField(default=None, max_length=50, choices=[(b'dwolla', b'Dwolla'), (b'paypal', b'PayPal'), (b'cc', b'Credit Card'), (b'check', b'Check')])),
                ('payment_id', models.CharField(max_length=64, verbose_name=b'Internal ID used during a transaction')),
                ('transaction_id', models.CharField(max_length=64, null=True, blank=True)),
                ('status', models.SmallIntegerField(choices=[(0, b'Awaiting Payment'), (1, b'Unknown Error'), (2, b'Completed, but awaiting processing'), (3, b'Cancelled'), (4, b'Processed'), (5, b'Pending'), (6, b'Failed'), (7, b'Reclaimed/Refunded'), (8, b'Captured')])),
                ('referrer', models.TextField(verbose_name=b'GET or HTTP referrer', blank=True)),
            ],
            options={
                'ordering': ['-date_created'],
            },
        ),
    ]
