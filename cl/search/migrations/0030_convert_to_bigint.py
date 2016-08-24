# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0029_auto_20160818_1645'),
    ]

    operations = [
        migrations.AlterField(
            model_name='docketentry',
            name='entry_number',
            field=models.BigIntegerField(help_text=b'# on the PACER docket page.'),
        ),
    ]
