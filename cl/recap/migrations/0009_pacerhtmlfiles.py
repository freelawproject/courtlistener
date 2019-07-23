# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import cl.recap.models
import cl.lib.storage


class Migration(migrations.Migration):

    dependencies = [
        ('contenttypes', '0002_remove_content_type_name'),
        ('recap', '0008_auto_20170916_2251'),
    ]

    operations = [
        migrations.CreateModel(
            name='PacerHtmlFiles',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('date_created', models.DateTimeField(help_text=b'The time when this item was created', auto_now_add=True, db_index=True)),
                ('date_modified', models.DateTimeField(help_text=b'The last moment when the item was modified.', auto_now=True, db_index=True)),
                ('filepath', models.FileField(help_text=b'The path of the original data from PACER.', storage=cl.lib.storage.UUIDFileSystemStorage(), max_length=150, upload_to=cl.recap.models.make_recap_data_path)),
                ('object_id', models.PositiveIntegerField()),
                ('content_type', models.ForeignKey(to='contenttypes.ContentType',
                                                   on_delete=models.CASCADE)),
            ],
        ),
    ]
