# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('people_db', '0022_auto_20160723_0647'),
    ]

    operations = [
        migrations.AddField(
            model_name='position',
            name='has_inferred_values',
            field=models.BooleanField(default=False, help_text=b'Some or all of the values for this position were inferred from a data source instead of manually added. See sources field for more details.'),
        ),
        migrations.AlterField(
            model_name='position',
            name='position_type',
            field=models.CharField(blank=True, max_length=20, null=True, help_text=b'If this is a judicial position, this indicates the role the person had. This field may be blank if job_title is complete instead.', choices=[(b'Judge', ((b'act-jud', b'Acting Judge'), (b'act-pres-jud', b'Acting Presiding Judge'), (b'ass-jud', b'Associate Judge'), (b'ass-c-jud', b'Associate Chief Judge'), (b'ass-pres-jud', b'Associate Presiding Judge'), (b'jud', b'Judge'), (b'jus', b'Justice'), (b'c-jud', b'Chief Judge'), (b'c-jus', b'Chief Justice'), (b'c-mag', b'Chief Magistrate'), (b'c-spec-m', b'Chief Special Master'), (b'pres-jud', b'Presiding Judge'), (b'pres-jus', b'Presiding Justice'), (b'pres-mag', b'Presiding Magistrate'), (b'com', b'Commissioner'), (b'com-dep', b'Deputy Commissioner'), (b'jud-pt', b'Judge Pro Tem'), (b'jus-pt', b'Justice Pro Tem'), (b'mag-pt', b'Magistrate Pro Tem'), (b'ref-jud-tr', b'Judge Trial Referee'), (b'ref-off', b'Official Referee'), (b'ref-state-trial', b'State Trial Referee'), (b'ret-act-jus', b'Active Retired Justice'), (b'ret-ass-jud', b'Retired Associate Judge'), (b'ret-c-jud', b'Retired Chief Judge'), (b'ret-jus', b'Retired Justice'), (b'ret-senior-jud', b'Senior Judge'), (b'spec-chair', b'Special Chairman'), (b'spec-jud', b'Special Judge'), (b'spec-m', b'Special Master'), (b'spec-scjcbc', b'Special Superior Court Judge for Complex Business Cases'), (b'chair', b'Chairman'), (b'chan', b'Chancellor'), (b'mag', b'Magistrate'), (b'presi-jud', b'President'), (b'res-jud', b'Reserve Judge'), (b'trial-jud', b'Trial Judge'), (b'vice-chan', b'Vice Chancellor'), (b'vice-cj', b'Vice Chief Judge'))), (b'Attorney General', ((b'att-gen', b'Attorney General'), (b'att-gen-ass', b'Assistant Attorney General'), (b'att-gen-ass-spec', b'Special Assistant Attorney General'), (b'sen-counsel', b'Senior Counsel'), (b'dep-sol-gen', b'Deputy Solicitor General'))), (b'Appointing Authority', ((b'pres', b'President of the United States'), (b'gov', b'Governor'))), (b'Clerkships', ((b'clerk', b'Clerk'), (b'staff-atty', b'Staff Attorney'))), (b'prof', b'Professor'), (b'prac', b'Practitioner'), (b'pros', b'Prosecutor'), (b'pub_def', b'Public Defender'), (b'legis', b'Legislator')]),
        ),
    ]
