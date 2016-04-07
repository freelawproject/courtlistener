# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0007_auto_20160331_0510'),
    ]

    operations = [
        migrations.AlterField(
            model_name='recapdocument',
            name='pacer_doc_id',
            field=models.CharField(help_text=b'The ID of the document in PACER. This information is provided by RECAP.', max_length=32),
        ),
    ]
