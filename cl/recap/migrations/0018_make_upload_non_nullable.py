# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('recap', '0017_add_upload_type_to_pacer_html_files'),
    ]

    operations = [
        migrations.AlterField(
            model_name='pacerhtmlfiles',
            name='upload_type',
            field=models.SmallIntegerField(default=1, help_text=b'The type of object that is uploaded', choices=[(1, b'HTML Docket'), (2, b'HTML attachment page'), (3, b'PDF'), (4, b'Docket history report'), (5, b'Appellate HTML docket'), (6, b'Appellate HTML attachment page')]),
            preserve_default=False,
        ),
    ]
