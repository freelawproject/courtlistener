# -*- coding: utf-8 -*-


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
                ('send_annual_reminder', models.BooleanField(default=False, verbose_name='Send me a reminder to donate again in one year')),
                ('amount', models.DecimalField(default=None, max_digits=10, decimal_places=2)),
                ('payment_provider', models.CharField(default=None, max_length=50, choices=[('dwolla', 'Dwolla'), ('paypal', 'PayPal'), ('cc', 'Credit Card'), ('check', 'Check')])),
                ('payment_id', models.CharField(max_length=64, verbose_name='Internal ID used during a transaction')),
                ('transaction_id', models.CharField(max_length=64, null=True, blank=True)),
                ('status', models.SmallIntegerField(choices=[(0, 'Awaiting Payment'), (1, 'Unknown Error'), (2, 'Completed, but awaiting processing'), (3, 'Cancelled'), (4, 'Processed'), (5, 'Pending'), (6, 'Failed'), (7, 'Reclaimed/Refunded'), (8, 'Captured')])),
                ('referrer', models.TextField(verbose_name='GET or HTTP referrer', blank=True)),
            ],
            options={
                'ordering': ['-date_created'],
            },
        ),
    ]
