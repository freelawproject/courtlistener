# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('people_db', '0017_auto_20160419_0705'),
    ]

    operations = [
        migrations.AlterField(
            model_name='education',
            name='degree_detail',
            field=models.CharField(help_text=b'Detailed degree description, e.g. including major.', max_length=100, blank=True),
        ),
        migrations.AlterField(
            model_name='education',
            name='degree_level',
            field=models.CharField(blank=True, help_text=b'Normalized degree level, e.g. BA, JD.', max_length=4, choices=[(b'ba', b"Bachelor's (e.g. B.A.)"), (b'ma', b"Master's (e.g. M.A.)"), (b'jd', b'Juris Doctor (J.D.)'), (b'llm', b'Master of Laws (LL.M)'), (b'llb', b'Bachelor of Laws (e.g. LL.B)'), (b'jsd', b'Doctor of Law (J.S.D)'), (b'phd', b'Doctor of Philosophy (PhD)'), (b'aa', b'Associate (e.g. A.A.)'), (b'md', b'Medical Degree (M.D.)'), (b'mba', b'Master of Business Administration (M.B.A.)'), (b'cfa', b'Accounting Certification (C.P.A., C.M.A., C.F.A.)'), (b'cert', b'Certificate')]),
        ),
    ]
