# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0012_make_pacer_id_nullable'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='docketentry',
            options={'verbose_name_plural': 'Docket Entries'},
        ),
        migrations.AddField(
            model_name='docketentry',
            name='description_short',
            field=models.TextField(default='', help_text=b'The short description of the docket entry that appears on the docket page.'),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='docketentry',
            name='description',
            field=models.TextField(help_text=b'The text content of the docket entry that appears in the PACER docket page.'),
        ),
    ]
