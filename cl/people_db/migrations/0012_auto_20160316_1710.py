# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('people_db', '0011_auto_20160229_1248'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='person',
            options={'verbose_name_plural': 'people'},
        ),
        migrations.AlterField(
            model_name='position',
            name='how_selected',
            field=models.CharField(blank=True, max_length=20, choices=[(b'e_part', b'Partisan Election'), (b'e_non_part', b'Non-Partisan Election'), (b'a_pres', b'Appointment (President)'), (b'a_gov', b'Appointment (Governor)'), (b'a_legis', b'Appointment (Legislature)')]),
        ),
        migrations.AlterField(
            model_name='position',
            name='job_title',
            field=models.CharField(help_text=b"If title isn't in list, type here.", max_length=100, blank=True),
        ),
        migrations.AlterField(
            model_name='position',
            name='position_type',
            field=models.CharField(blank=True, max_length=20, null=True, choices=[(b'Judge', ((b'act-jud', b'Acting Judge'), (b'act-pres-jud', b'Acting Presiding Judge'), (b'ass-jud', b'Associate Judge'), (b'ass-c-jud', b'Associate Chief Judge'), (b'ass-pres-jud', b'Associate Presiding Judge'), (b'jud', b'Judge'), (b'jus', b'Justice'), (b'c-jud', b'Chief Judge'), (b'c-jus', b'Chief Justice'), (b'pres-jud', b'Presiding Judge'), (b'pres-jus', b'Presiding Justice'), (b'pres-mag', b'Presiding Magistrate'), (b'com', b'Commissioner'), (b'com-dep', b'Deputy Commissioner'), (b'jud-pt', b'Judge Pro Tem'), (b'jus-pt', b'Justice Pro Tem'), (b'mag-pt', b'Magistrate Pro Tem'), (b'ref-jud-tr', b'Judge Trial Referee'), (b'ref-off', b'Official Referee'), (b'ref-state-trial', b'State Trial Referee'), (b'ret-act-jus', b'Active Retired Justice'), (b'ret-ass-jud', b'Retired Associate Judge'), (b'ret-c-jud', b'Retired Chief Judge'), (b'ret-jus', b'Retired Justice'), (b'ret-senior-jud', b'Senior Judge'), (b'spec-chair', b'Special Chairman'), (b'spec-jud', b'Special Judge'), (b'spec-m', b'Special Master'), (b'spec-scjcbc', b'Special Superior Court Judge for Complex Business Cases'), (b'chair', b'Chairman'), (b'chan', b'Chancellor'), (b'mag', b'Magistrate'), (b'presi-jud', b'President'), (b'res-jud', b'Reserve Judge'), (b'trial-jud', b'Trial Judge'), (b'vice-chan', b'Vice Chancellor'), (b'vice-cj', b'Vice Chief Judge'))), (b'Attorney General', ((b'att-gen', b'Attorney General'), (b'att-gen-ass', b'Assistant Attorney General'), (b'att-gen-ass-spec', b'Special Assistant Attorney General'), (b'sen-counsel', b'Senior Counsel'), (b'dep-sol-gen', b'Deputy Solicitor General'))), (b'Appointing Authority', ((b'pres', b'President'), (b'gov', b'Governor'))), (b'Clerkships', ((b'clerk', b'Clerk'), (b'staff-atty', b'Staff Attorney'))), (b'prof', b'Professor'), (b'prac', b'Practitioner'), (b'pros', b'Prosecutor'), (b'pub_def', b'Public Defender'), (b'legis', b'Legislator')]),
        ),
    ]
