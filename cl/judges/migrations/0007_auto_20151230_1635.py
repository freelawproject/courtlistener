# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('judges', '0006_auto_20151221_1551'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='abarating',
            options={'permissions': (('has_beta_api_access', 'Can access features during beta period.'),)},
        ),
        migrations.AlterModelOptions(
            name='career',
            options={'ordering': ['date_start'], 'permissions': (('has_beta_api_access', 'Can access features during beta period.'),)},
        ),
        migrations.AlterModelOptions(
            name='education',
            options={'permissions': (('has_beta_api_access', 'Can access features during beta period.'),)},
        ),
        migrations.AlterModelOptions(
            name='judge',
            options={'permissions': (('has_beta_api_access', 'Can access features during beta period.'),)},
        ),
        migrations.AlterModelOptions(
            name='politicalaffiliation',
            options={'permissions': (('has_beta_api_access', 'Can access features during beta period.'),)},
        ),
        migrations.AlterModelOptions(
            name='politician',
            options={'permissions': (('has_beta_api_access', 'Can access features during beta period.'),)},
        ),
        migrations.AlterModelOptions(
            name='position',
            options={'permissions': (('has_beta_api_access', 'Can access features during beta period.'),)},
        ),
        migrations.AlterModelOptions(
            name='race',
            options={'permissions': (('has_beta_api_access', 'Can access features during beta period.'),)},
        ),
        migrations.AlterModelOptions(
            name='retentionevent',
            options={'permissions': (('has_beta_api_access', 'Can access features during beta period.'),)},
        ),
        migrations.AlterModelOptions(
            name='school',
            options={'permissions': (('has_beta_api_access', 'Can access features during beta period.'),)},
        ),
        migrations.AlterModelOptions(
            name='source',
            options={'permissions': (('has_beta_api_access', 'Can access features during beta period.'),)},
        ),
        migrations.AlterModelOptions(
            name='title',
            options={'permissions': (('has_beta_api_access', 'Can access features during beta period.'),)},
        ),
    ]
