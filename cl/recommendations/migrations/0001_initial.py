# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0062_add_indexes_to_title_section_fields'),
    ]

    operations = [
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
    ]
