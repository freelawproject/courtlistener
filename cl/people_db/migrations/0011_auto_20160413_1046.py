# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('people_db', '0010_auto_20160412_1625'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='abarating',
            options={},
        ),
        migrations.RemoveField(
            model_name='abarating',
            name='date_granularity_rated',
        ),
        migrations.RemoveField(
            model_name='abarating',
            name='date_rated',
        ),
        migrations.AddField(
            model_name='abarating',
            name='year_rated',
            field=models.PositiveSmallIntegerField(help_text=b'The year of the rating.', null=True),
        ),
        migrations.AddField(
            model_name='position',
            name='vote_type',
            field=models.CharField(blank=True, max_length=2, choices=[(b's', b'Senate'), (b'p', b'Partisan Election'), (b'np', b'Non-Partisan Election')]),
        ),
        migrations.AddField(
            model_name='position',
            name='votes_no_percent',
            field=models.FloatField(null=True, blank=True),
        ),
        migrations.AddField(
            model_name='position',
            name='votes_yes_percent',
            field=models.FloatField(null=True, blank=True),
        ),
        migrations.AddField(
            model_name='retentionevent',
            name='votes_no_percent',
            field=models.FloatField(null=True, blank=True),
        ),
        migrations.AddField(
            model_name='retentionevent',
            name='votes_yes_percent',
            field=models.FloatField(null=True, blank=True),
        ),
        migrations.AlterField(
            model_name='position',
            name='votes_no',
            field=models.PositiveIntegerField(null=True, blank=True),
        ),
        migrations.AlterField(
            model_name='position',
            name='votes_yes',
            field=models.PositiveIntegerField(null=True, blank=True),
        ),
        migrations.AlterField(
            model_name='retentionevent',
            name='votes_no',
            field=models.PositiveIntegerField(null=True, blank=True),
        ),
        migrations.AlterField(
            model_name='retentionevent',
            name='votes_yes',
            field=models.PositiveIntegerField(null=True, blank=True),
        ),
    ]
