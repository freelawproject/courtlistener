# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0001_initial'),
        ('people_db', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='position',
            name='court',
            field=models.ForeignKey(related_name='court_positions', blank=True, to='search.Court', null=True),
        ),
        migrations.AddField(
            model_name='position',
            name='person',
            field=models.ForeignKey(related_name='positions', blank=True, to='people_db.Person', null=True),
        ),
        migrations.AddField(
            model_name='position',
            name='predecessor',
            field=models.ForeignKey(blank=True, to='people_db.Person', null=True),
        ),
        migrations.AddField(
            model_name='position',
            name='school',
            field=models.ForeignKey(blank=True, to='people_db.School', help_text=b'If academic job, the school where they work.', null=True),
        ),
        migrations.AddField(
            model_name='position',
            name='supervisor',
            field=models.ForeignKey(related_name='supervised_positions', blank=True, to='people_db.Person', help_text=b'If this is a clerkship, the supervising judge.', null=True),
        ),
        migrations.AddField(
            model_name='politicalaffiliation',
            name='person',
            field=models.ForeignKey(related_name='political_affiliations', blank=True, to='people_db.Person', null=True),
        ),
        migrations.AddField(
            model_name='person',
            name='is_alias_of',
            field=models.ForeignKey(blank=True, to='people_db.Person', null=True),
        ),
        migrations.AddField(
            model_name='person',
            name='race',
            field=models.ManyToManyField(to='people_db.Race', blank=True),
        ),
        migrations.AddField(
            model_name='education',
            name='person',
            field=models.ForeignKey(related_name='educations', blank=True, to='people_db.Person', null=True),
        ),
        migrations.AddField(
            model_name='education',
            name='school',
            field=models.ForeignKey(related_name='educations', to='people_db.School'),
        ),
        migrations.AddField(
            model_name='abarating',
            name='person',
            field=models.ForeignKey(related_name='aba_ratings', blank=True, to='people_db.Person', null=True),
        ),
    ]
