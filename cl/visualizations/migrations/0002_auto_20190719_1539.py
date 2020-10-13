# -*- coding: utf-8 -*-
# Generated by Django 1.11.22 on 2019-07-19 19:39


from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('visualizations', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='referer',
            name='url',
            field=models.URLField(db_index=True, help_text='The URL where this item was embedded.', max_length=3000),
        ),
    ]
