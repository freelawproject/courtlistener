# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('donate', '0002_donation_donor'),
    ]

    operations = [
        migrations.AlterField(
            model_name='donation',
            name='payment_provider',
            field=models.CharField(default=None, max_length=50, choices=[(b'dwolla', b'Dwolla'), (b'paypal', b'PayPal'), (b'cc', b'Credit Card'), (b'check', b'Check'), (b'bitcoin', b'Bitcoin')]),
        ),
    ]
