# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0038_auto_20160906_1613'),
    ]

    operations = [
        migrations.AlterField(
            model_name='opinioncluster',
            name='precedential_status',
            field=models.CharField(blank=True, help_text=b'The precedential status of document, one of: Published, Unpublished, Errata, Separate, In-chambers, Relating-to, Unknown', max_length=50, db_index=True, choices=[(b'Published', b'Precedential'), (b'Unpublished', b'Non-Precedential'), (b'Errata', b'Errata'), (b'Separate', b'Separate Opinion'), (b'In-chambers', b'In-chambers'), (b'Relating-to', b'Relating-to orders'), (b'Unknown', b'Unknown Status')]),
        ),
    ]
