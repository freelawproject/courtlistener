# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0039_auto_20161024_1500'),
    ]

    operations = [
        migrations.AddField(
            model_name='opinion',
            name='author_str',
            field=models.TextField(help_text=b'The primary author of this opinion, as a simple text string. This field is used when normalized judges cannot be placed into the author field.', blank=True),
        ),
        migrations.AlterField(
            model_name='opinion',
            name='author',
            field=models.ForeignKey(related_name='opinions_written', blank=True, to='people_db.Person', help_text=b'The primary author of this opinion as a normalized field', null=True),
        ),
        migrations.AlterField(
            model_name='opinioncluster',
            name='date_filed',
            field=models.DateField(help_text=b'The date the cluster of opinions was filed by the court', db_index=True),
        ),
    ]
