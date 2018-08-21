# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('donate', '0005_add_failure_count_to_m_donations'),
    ]

    operations = [
        migrations.AlterField(
            model_name='donation',
            name='amount',
            field=models.DecimalField(default=None, max_digits=10, decimal_places=2, validators=[django.core.validators.MinValueValidator(5, b'Sorry, the minimum donation amount is $5.00.')]),
        ),
    ]
