# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('audio', '0005_auto_20161103_1436'),
        ('people_db', '0036_remove_unique_constraint_on_party_name'),
        ('search', '0063_add_pacer_rss_field'),
    ]

    operations = [
        migrations.CreateModel(
            name='AudioRecommendation',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('score', models.DecimalField(max_digits=12, decimal_places=8)),
                ('recommendation', models.ForeignKey(related_name='recommendation_id', to='audio.Audio')),
                ('seed', models.ForeignKey(related_name='seed_id', to='audio.Audio')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='DocketRecommendation',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('score', models.DecimalField(max_digits=12, decimal_places=8)),
                ('recommendation', models.ForeignKey(related_name='recommendation_id', to='search.Docket')),
                ('seed', models.ForeignKey(related_name='seed_id', to='search.Docket')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='OpinionRecommendation',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('score', models.DecimalField(max_digits=12, decimal_places=8)),
                ('recommendation', models.ForeignKey(related_name='recommendation_id', to='search.Opinion')),
                ('seed', models.ForeignKey(related_name='seed_id', to='search.Opinion')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='PersonRecommendation',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('score', models.DecimalField(max_digits=12, decimal_places=8)),
                ('recommendation', models.ForeignKey(related_name='recommendation_id', to='people_db.Person')),
                ('seed', models.ForeignKey(related_name='seed_id', to='people_db.Person')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.AlterUniqueTogether(
            name='personrecommendation',
            unique_together=set([('seed', 'recommendation')]),
        ),
        migrations.AlterUniqueTogether(
            name='opinionrecommendation',
            unique_together=set([('seed', 'recommendation')]),
        ),
        migrations.AlterUniqueTogether(
            name='docketrecommendation',
            unique_together=set([('seed', 'recommendation')]),
        ),
        migrations.AlterUniqueTogether(
            name='audiorecommendation',
            unique_together=set([('seed', 'recommendation')]),
        ),
    ]
