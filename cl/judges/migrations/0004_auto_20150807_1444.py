# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('judges', '0003_auto_20150713_1218'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='judge',
            name='aba_rating',
        ),
        migrations.RemoveField(
            model_name='judge',
            name='career',
        ),
        migrations.RemoveField(
            model_name='judge',
            name='education',
        ),
        migrations.RemoveField(
            model_name='judge',
            name='judge_position',
        ),
        migrations.RemoveField(
            model_name='judge',
            name='political_affiliation',
        ),
        migrations.RemoveField(
            model_name='judge',
            name='source',
        ),
        migrations.RemoveField(
            model_name='judge',
            name='title',
        ),
        migrations.RemoveField(
            model_name='politician',
            name='political_party',
        ),
        migrations.RemoveField(
            model_name='position',
            name='retention_event',
        ),
        migrations.AddField(
            model_name='abarating',
            name='judge',
            field=models.ForeignKey(related_name='aba_ratings', blank=True, to='judges.Judge', null=True),
        ),
        migrations.AddField(
            model_name='career',
            name='judge',
            field=models.ForeignKey(related_name='careers', blank=True, to='judges.Judge', null=True),
        ),
        migrations.AddField(
            model_name='education',
            name='judge',
            field=models.ForeignKey(related_name='educations', blank=True, to='judges.Judge', null=True),
        ),
        migrations.AddField(
            model_name='politicalaffiliation',
            name='judge',
            field=models.ForeignKey(related_name='political_affiliations', blank=True, to='judges.Judge', null=True),
        ),
        migrations.AddField(
            model_name='politicalaffiliation',
            name='politician',
            field=models.ForeignKey(related_name='political_affiliations', blank=True, to='judges.Politician', null=True),
        ),
        migrations.AddField(
            model_name='position',
            name='judge',
            field=models.ForeignKey(related_name='positions', blank=True, to='judges.Judge', null=True),
        ),
        migrations.AddField(
            model_name='retentionevent',
            name='position',
            field=models.ForeignKey(related_name='retention_events', blank=True, to='judges.Position', null=True),
        ),
        migrations.AddField(
            model_name='source',
            name='judge',
            field=models.ForeignKey(related_name='sources', blank=True, to='judges.Judge', null=True),
        ),
        migrations.AddField(
            model_name='title',
            name='judge',
            field=models.ForeignKey(related_name='titles', blank=True, to='judges.Judge', null=True),
        ),
        migrations.AlterField(
            model_name='position',
            name='court',
            field=models.ForeignKey(related_name='+', to='search.Court'),
        ),
    ]
