# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0001_initial'),
        ('judges', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='position',
            name='court',
            field=models.ForeignKey(related_name='judge_position', to='search.Court'),
        ),
        migrations.AddField(
            model_name='position',
            name='predecessor',
            field=models.ForeignKey(blank=True, to='judges.Judge', null=True),
        ),
        migrations.AddField(
            model_name='position',
            name='retention_event',
            field=models.ForeignKey(blank=True, to='judges.RetentionEvent', null=True),
        ),
        migrations.AddField(
            model_name='politician',
            name='political_party',
            field=models.ForeignKey(to='judges.PoliticalAffiliation', blank=True),
        ),
        migrations.AddField(
            model_name='judge',
            name='aba_rating',
            field=models.ForeignKey(blank=True, to='judges.ABARating', null=True),
        ),
        migrations.AddField(
            model_name='judge',
            name='career',
            field=models.ForeignKey(blank=True, to='judges.Career', null=True),
        ),
        migrations.AddField(
            model_name='judge',
            name='education',
            field=models.ForeignKey(blank=True, to='judges.Education', null=True),
        ),
        migrations.AddField(
            model_name='judge',
            name='is_alias_of',
            field=models.ForeignKey(blank=True, to='judges.Judge', null=True),
        ),
        migrations.AddField(
            model_name='judge',
            name='judge_position',
            field=models.ForeignKey(blank=True, to='judges.Position', null=True),
        ),
        migrations.AddField(
            model_name='judge',
            name='political_affiliation',
            field=models.ForeignKey(blank=True, to='judges.PoliticalAffiliation', null=True),
        ),
        migrations.AddField(
            model_name='judge',
            name='race',
            field=models.ManyToManyField(to='judges.Race', blank=True),
        ),
        migrations.AddField(
            model_name='judge',
            name='source',
            field=models.ForeignKey(blank=True, to='judges.Source', null=True),
        ),
        migrations.AddField(
            model_name='judge',
            name='title',
            field=models.ForeignKey(blank=True, to='judges.Title', null=True),
        ),
        migrations.AddField(
            model_name='education',
            name='school',
            field=models.ForeignKey(to='judges.School'),
        ),
    ]
