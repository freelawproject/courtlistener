# -*- coding: utf-8 -*-


from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('people_db', '0016_auto_20160416_1111'),
    ]

    operations = [
        migrations.AlterField(
            model_name='education',
            name='degree_level',
            field=models.CharField(blank=True, max_length=4, choices=[('ba', "Bachelor's (e.g. B.A.)"), ('ma', "Master's (e.g. M.A.)"), ('jd', 'Juris Doctor (J.D.)'), ('llm', 'Master of Laws (LL.M)'), ('llb', 'Bachelor of Laws (e.g. LL.B)'), ('jsd', 'Doctor of Law (J.S.D)'), ('phd', 'Doctor of Philosophy (PhD)'), ('aa', 'Associate (e.g. A.A.)'), ('md', 'Medical Degree (M.D.)'), ('mba', 'Master of Business Administration (M.B.A.)'), ('cfa', 'Accounting Certification (C.P.A., C.M.A., C.F.A.)'), ('cert', 'Certificate')]),
        ),
    ]
