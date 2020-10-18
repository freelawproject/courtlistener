# -*- coding: utf-8 -*-


from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('people_db', '0022_auto_20160723_0647'),
    ]

    operations = [
        migrations.AddField(
            model_name='position',
            name='has_inferred_values',
            field=models.BooleanField(default=False, help_text='Some or all of the values for this position were inferred from a data source instead of manually added. See sources field for more details.'),
        ),
        migrations.AlterField(
            model_name='position',
            name='position_type',
            field=models.CharField(blank=True, max_length=20, null=True, help_text='If this is a judicial position, this indicates the role the person had. This field may be blank if job_title is complete instead.', choices=[('Judge', (('act-jud', 'Acting Judge'), ('act-pres-jud', 'Acting Presiding Judge'), ('ass-jud', 'Associate Judge'), ('ass-c-jud', 'Associate Chief Judge'), ('ass-pres-jud', 'Associate Presiding Judge'), ('jud', 'Judge'), ('jus', 'Justice'), ('c-jud', 'Chief Judge'), ('c-jus', 'Chief Justice'), ('c-mag', 'Chief Magistrate'), ('c-spec-m', 'Chief Special Master'), ('pres-jud', 'Presiding Judge'), ('pres-jus', 'Presiding Justice'), ('pres-mag', 'Presiding Magistrate'), ('com', 'Commissioner'), ('com-dep', 'Deputy Commissioner'), ('jud-pt', 'Judge Pro Tem'), ('jus-pt', 'Justice Pro Tem'), ('mag-pt', 'Magistrate Pro Tem'), ('ref-jud-tr', 'Judge Trial Referee'), ('ref-off', 'Official Referee'), ('ref-state-trial', 'State Trial Referee'), ('ret-act-jus', 'Active Retired Justice'), ('ret-ass-jud', 'Retired Associate Judge'), ('ret-c-jud', 'Retired Chief Judge'), ('ret-jus', 'Retired Justice'), ('ret-senior-jud', 'Senior Judge'), ('spec-chair', 'Special Chairman'), ('spec-jud', 'Special Judge'), ('spec-m', 'Special Master'), ('spec-scjcbc', 'Special Superior Court Judge for Complex Business Cases'), ('chair', 'Chairman'), ('chan', 'Chancellor'), ('mag', 'Magistrate'), ('presi-jud', 'President'), ('res-jud', 'Reserve Judge'), ('trial-jud', 'Trial Judge'), ('vice-chan', 'Vice Chancellor'), ('vice-cj', 'Vice Chief Judge'))), ('Attorney General', (('att-gen', 'Attorney General'), ('att-gen-ass', 'Assistant Attorney General'), ('att-gen-ass-spec', 'Special Assistant Attorney General'), ('sen-counsel', 'Senior Counsel'), ('dep-sol-gen', 'Deputy Solicitor General'))), ('Appointing Authority', (('pres', 'President of the United States'), ('gov', 'Governor'))), ('Clerkships', (('clerk', 'Clerk'), ('staff-atty', 'Staff Attorney'))), ('prof', 'Professor'), ('prac', 'Practitioner'), ('pros', 'Prosecutor'), ('pub_def', 'Public Defender'), ('legis', 'Legislator')]),
        ),
    ]
