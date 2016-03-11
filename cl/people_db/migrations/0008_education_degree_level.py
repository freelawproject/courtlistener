# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('people_db', '0007_auto_20160227_0921'),
    ]

    operations = [
        migrations.AddField(
            model_name='education',
            name='degree_level',
            field=models.CharField(default='ba', max_length=2, choices=[(b'ba', b"Bachelor's (B.A./B.S.)"), (b'ma', b"Master's (M.A./M.S./etc.)"), (b'jd', b'Juris Doctor (J.D.)'), (b'llm', b'Master of Laws (LL.M)'), (b'llb', b'Bachelor of Laws (LL.B)'), (b'phd', b'Doctor of Philosophy (PhD)'), (b'aa', b'Associate (A.A./A.S)')]),
            preserve_default=False,
        ),
    ]
