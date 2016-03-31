# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('people_db', '0004_load_races'),
    ]

    operations = [
        migrations.AddField(
            model_name='person',
            name='religion',
            field=models.CharField(blank=True, max_length=2, choices=[(b'ca', b'Catholic'), (b'pr', b'Protestant'), (b'je', b'Jewish'), (b'mu', b'Muslim'), (b'at', b'Atheist'), (b'ag', b'Agnostic'), (b'mo', b'Mormon'), (b'bu', b'Buddhist'), (b'hi', b'Hindu')]),
        ),
        migrations.AlterField(
            model_name='education',
            name='degree_level',
            field=models.CharField(blank=True, max_length=3, choices=[(b'ba', b"Bachelor's (e.g. B.A.)"), (b'ma', b"Master's (e.g. M.A.)"), (b'jd', b'Juris Doctor (J.D.)'), (b'llm', b'Master of Laws (LL.M)'), (b'llb', b'Bachelor of Laws (e.g. LL.B)'), (b'jsd', b'Doctor of Law (J.S.D)'), (b'phd', b'Doctor of Philosophy (PhD)'), (b'aa', b'Associate (e.g. A.A.)'), (b'md', b'Medical Degree (M.D.)'), (b'mba', b'Master of Business Administration (M.B.A.)')]),
        ),
        migrations.AlterField(
            model_name='person',
            name='gender',
            field=models.CharField(blank=True, max_length=2, choices=[(b'm', b'Male'), (b'f', b'Female'), (b'o', b'Other')]),
        ),
        migrations.AlterField(
            model_name='race',
            name='race',
            field=models.CharField(unique=True, max_length=5, choices=[(b'w', b'White'), (b'b', b'Black or African American'), (b'i', b'American Indian or Alaska Native'), (b'a', b'Asian'), (b'p', b'Native Hawaiian or Other Pacific Islander'), (b'h', b'Hispanic/Latino')]),
        ),
    ]
