# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('donate', '0003_add_bitcoin'),
    ]

    operations = [
        migrations.CreateModel(
            name='MonthlyDonation',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('date_modified', models.DateTimeField(auto_now=True, db_index=True)),
                ('date_created', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('enabled', models.BooleanField(default=True, help_text=b'Is this monthly donation enabled?')),
                ('payment_provider', models.CharField(max_length=50, choices=[(b'dwolla', b'Dwolla'), (b'paypal', b'PayPal'), (b'cc', b'Credit Card'), (b'check', b'Check'), (b'bitcoin', b'Bitcoin')])),
                ('monthly_donation_amount', models.DecimalField(max_digits=10, decimal_places=2)),
                ('monthly_donation_day', models.SmallIntegerField(help_text=b'The day of the month that the monthly donation should be processed.')),
                ('stripe_customer_id', models.CharField(help_text=b'The ID of the Stripe customer object that we use to charge credit card users each month.', max_length=200)),
                ('donor', models.ForeignKey(related_name='monthly_donations', to=settings.AUTH_USER_MODEL, help_text=b'The user that made the donation',
                                            on_delete=models.CASCADE)),
            ],
        ),
        migrations.AlterField(
            model_name='donation',
            name='payment_id',
            field=models.CharField(help_text=b'Internal ID used during a transaction (used by PayPal and Stripe).', max_length=64),
        ),
        migrations.AlterField(
            model_name='donation',
            name='transaction_id',
            field=models.CharField(help_text=b'The ID of a transaction made in PayPal.', max_length=64, null=True, blank=True),
        ),
    ]
