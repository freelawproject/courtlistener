# -*- coding: utf-8 -*-


from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('people_db', '0004_load_races'),
    ]

    operations = [
        migrations.AddField(
            model_name='person',
            name='religion',
            field=models.CharField(blank=True, max_length=2, choices=[('ca', 'Catholic'), ('pr', 'Protestant'), ('je', 'Jewish'), ('mu', 'Muslim'), ('at', 'Atheist'), ('ag', 'Agnostic'), ('mo', 'Mormon'), ('bu', 'Buddhist'), ('hi', 'Hindu')]),
        ),
        migrations.AlterField(
            model_name='education',
            name='degree_level',
            field=models.CharField(blank=True, max_length=3, choices=[('ba', "Bachelor's (e.g. B.A.)"), ('ma', "Master's (e.g. M.A.)"), ('jd', 'Juris Doctor (J.D.)'), ('llm', 'Master of Laws (LL.M)'), ('llb', 'Bachelor of Laws (e.g. LL.B)'), ('jsd', 'Doctor of Law (J.S.D)'), ('phd', 'Doctor of Philosophy (PhD)'), ('aa', 'Associate (e.g. A.A.)'), ('md', 'Medical Degree (M.D.)'), ('mba', 'Master of Business Administration (M.B.A.)')]),
        ),
        migrations.AlterField(
            model_name='person',
            name='gender',
            field=models.CharField(blank=True, max_length=2, choices=[('m', 'Male'), ('f', 'Female'), ('o', 'Other')]),
        ),
        migrations.AlterField(
            model_name='race',
            name='race',
            field=models.CharField(unique=True, max_length=5, choices=[('w', 'White'), ('b', 'Black or African American'), ('i', 'American Indian or Alaska Native'), ('a', 'Asian'), ('p', 'Native Hawaiian or Other Pacific Islander'), ('h', 'Hispanic/Latino')]),
        ),
    ]
