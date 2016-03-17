# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('people_db', '0013_auto_20160316_1608'),
    ]

    operations = [
        migrations.AlterField(
            model_name='education',
            name='degree_level',
            field=models.CharField(blank=True, max_length=3, choices=[(b'ba', b"Bachelor's (e.g. B.A.)"), (b'ma', b"Master's (e.g. M.A.)"), (b'jd', b'Juris Doctor (J.D.)'), (b'llm', b'Master of Laws (LL.M)'), (b'llb', b'Bachelor of Laws (e.g. LL.B)'), (b'jsd', b'Doctor of Law (J.S.D)'), (b'phd', b'Doctor of Philosophy (PhD)'), (b'aa', b'Associate (e.g. A.A.)'), (b'md', b'Medical Degree (M.D.)'), (b'mba', b'Master of Business Administration (M.B.A.)')]),
        ),
    ]
