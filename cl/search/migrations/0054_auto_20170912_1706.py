# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0053_auto_20170906_1701'),
    ]

    operations = [
        migrations.CreateModel(
            name='Tag',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('date_created', models.DateTimeField(help_text=b'The original creation date for the item', auto_now_add=True, db_index=True)),
                ('date_modified', models.DateTimeField(help_text=b'The last moment when the item was modified. A value in year 1750 indicates the value is unknown', auto_now=True, db_index=True)),
                ('name', models.CharField(help_text=b'The name of the tag.', unique=True, max_length=50, db_index=True)),
            ],
        ),
        migrations.AddField(
            model_name='recapdocument',
            name='tags',
            field=models.ManyToManyField(help_text=b'The tags associated with the document.', related_name='recap_documents', to='search.Tag', blank=True),
        ),
    ]
