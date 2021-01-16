# -*- coding: utf-8 -*-


import localflavor.us.models
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='ABARating',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('date_created', models.DateTimeField(help_text='The original creation date for the item', auto_now_add=True, db_index=True)),
                ('date_modified', models.DateTimeField(help_text='The last moment when the item was modified.', auto_now=True, db_index=True)),
                ('date_rated', models.DateField(null=True, blank=True)),
                ('date_granularity_rated', models.CharField(blank=True, max_length=15, choices=[('%Y', 'Year'), ('%Y-%m', 'Month'), ('%Y-%m-%d', 'Day')])),
                ('rating', models.CharField(max_length=5, choices=[('ewq', 'Exceptionally Well Qualified'), ('wq', 'Well Qualified'), ('q', 'Qualified'), ('nq', 'Not Qualified'), ('nqa', 'Not Qualified By Reason of Age')])),
            ],
        ),
        migrations.CreateModel(
            name='Education',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('date_created', models.DateTimeField(help_text='The original creation date for the item', auto_now_add=True, db_index=True)),
                ('date_modified', models.DateTimeField(help_text='The last moment when the item was modified.', auto_now=True, db_index=True)),
                ('degree_level', models.CharField(blank=True, max_length=2, choices=[('ba', "Bachelor's (e.g. B.A.)"), ('ma', "Master's (e.g. M.A.)"), ('jd', 'Juris Doctor (J.D.)'), ('llm', 'Master of Laws (LL.M)'), ('llb', 'Bachelor of Laws (e.g. LL.B)'), ('jsd', 'Doctor of Law (J.S.D)'), ('phd', 'Doctor of Philosophy (PhD)'), ('aa', 'Associate (e.g. A.A.)'), ('md', 'Medical Degree (M.D.)'), ('mba', 'Master of Business Administration (M.B.A.)')])),
                ('degree', models.CharField(max_length=100, blank=True)),
                ('degree_year', models.PositiveSmallIntegerField(help_text='The year the degree was awarded.', null=True, blank=True)),
            ],
        ),
        migrations.CreateModel(
            name='Person',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('date_created', models.DateTimeField(help_text='The original creation date for the item', auto_now_add=True, db_index=True)),
                ('date_modified', models.DateTimeField(help_text='The last moment when the item was modified.', auto_now=True, db_index=True)),
                ('fjc_id', models.IntegerField(help_text='The ID of a judge as assigned by the Federal Judicial Center.', unique=True, null=True, db_index=True, blank=True)),
                ('slug', models.SlugField(max_length=158)),
                ('name_first', models.CharField(max_length=50)),
                ('name_middle', models.CharField(max_length=50, blank=True)),
                ('name_last', models.CharField(max_length=50, db_index=True)),
                ('name_suffix', models.CharField(blank=True, max_length=5, choices=[('jr', 'Jr.'), ('sr', 'Sr.'), ('1', 'I'), ('2', 'II'), ('3', 'III'), ('4', 'IV')])),
                ('date_dob', models.DateField(null=True, blank=True)),
                ('date_granularity_dob', models.CharField(blank=True, max_length=15, choices=[('%Y', 'Year'), ('%Y-%m', 'Month'), ('%Y-%m-%d', 'Day')])),
                ('date_dod', models.DateField(null=True, blank=True)),
                ('date_granularity_dod', models.CharField(blank=True, max_length=15, choices=[('%Y', 'Year'), ('%Y-%m', 'Month'), ('%Y-%m-%d', 'Day')])),
                ('dob_city', models.CharField(max_length=50, blank=True)),
                ('dob_state', localflavor.us.models.USStateField(blank=True, max_length=2, choices=[('AL', 'Alabama'), ('AK', 'Alaska'), ('AS', 'American Samoa'), ('AZ', 'Arizona'), ('AR', 'Arkansas'), ('AA', 'Armed Forces Americas'), ('AE', 'Armed Forces Europe'), ('AP', 'Armed Forces Pacific'), ('CA', 'California'), ('CO', 'Colorado'), ('CT', 'Connecticut'), ('DE', 'Delaware'), ('DC', 'District of Columbia'), ('FL', 'Florida'), ('GA', 'Georgia'), ('GU', 'Guam'), ('HI', 'Hawaii'), ('ID', 'Idaho'), ('IL', 'Illinois'), ('IN', 'Indiana'), ('IA', 'Iowa'), ('KS', 'Kansas'), ('KY', 'Kentucky'), ('LA', 'Louisiana'), ('ME', 'Maine'), ('MD', 'Maryland'), ('MA', 'Massachusetts'), ('MI', 'Michigan'), ('MN', 'Minnesota'), ('MS', 'Mississippi'), ('MO', 'Missouri'), ('MT', 'Montana'), ('NE', 'Nebraska'), ('NV', 'Nevada'), ('NH', 'New Hampshire'), ('NJ', 'New Jersey'), ('NM', 'New Mexico'), ('NY', 'New York'), ('NC', 'North Carolina'), ('ND', 'North Dakota'), ('MP', 'Northern Mariana Islands'), ('OH', 'Ohio'), ('OK', 'Oklahoma'), ('OR', 'Oregon'), ('PA', 'Pennsylvania'), ('PR', 'Puerto Rico'), ('RI', 'Rhode Island'), ('SC', 'South Carolina'), ('SD', 'South Dakota'), ('TN', 'Tennessee'), ('TX', 'Texas'), ('UT', 'Utah'), ('VT', 'Vermont'), ('VI', 'Virgin Islands'), ('VA', 'Virginia'), ('WA', 'Washington'), ('WV', 'West Virginia'), ('WI', 'Wisconsin'), ('WY', 'Wyoming')])),
                ('dod_city', models.CharField(max_length=50, blank=True)),
                ('dod_state', localflavor.us.models.USStateField(blank=True, max_length=2, choices=[('AL', 'Alabama'), ('AK', 'Alaska'), ('AS', 'American Samoa'), ('AZ', 'Arizona'), ('AR', 'Arkansas'), ('AA', 'Armed Forces Americas'), ('AE', 'Armed Forces Europe'), ('AP', 'Armed Forces Pacific'), ('CA', 'California'), ('CO', 'Colorado'), ('CT', 'Connecticut'), ('DE', 'Delaware'), ('DC', 'District of Columbia'), ('FL', 'Florida'), ('GA', 'Georgia'), ('GU', 'Guam'), ('HI', 'Hawaii'), ('ID', 'Idaho'), ('IL', 'Illinois'), ('IN', 'Indiana'), ('IA', 'Iowa'), ('KS', 'Kansas'), ('KY', 'Kentucky'), ('LA', 'Louisiana'), ('ME', 'Maine'), ('MD', 'Maryland'), ('MA', 'Massachusetts'), ('MI', 'Michigan'), ('MN', 'Minnesota'), ('MS', 'Mississippi'), ('MO', 'Missouri'), ('MT', 'Montana'), ('NE', 'Nebraska'), ('NV', 'Nevada'), ('NH', 'New Hampshire'), ('NJ', 'New Jersey'), ('NM', 'New Mexico'), ('NY', 'New York'), ('NC', 'North Carolina'), ('ND', 'North Dakota'), ('MP', 'Northern Mariana Islands'), ('OH', 'Ohio'), ('OK', 'Oklahoma'), ('OR', 'Oregon'), ('PA', 'Pennsylvania'), ('PR', 'Puerto Rico'), ('RI', 'Rhode Island'), ('SC', 'South Carolina'), ('SD', 'South Dakota'), ('TN', 'Tennessee'), ('TX', 'Texas'), ('UT', 'Utah'), ('VT', 'Vermont'), ('VI', 'Virgin Islands'), ('VA', 'Virginia'), ('WA', 'Washington'), ('WV', 'West Virginia'), ('WI', 'Wisconsin'), ('WY', 'Wyoming')])),
                ('gender', models.CharField(max_length=2, choices=[('m', 'Male'), ('f', 'Female'), ('o', 'Other')])),
            ],
            options={
                'verbose_name_plural': 'people',
            },
        ),
        migrations.CreateModel(
            name='PoliticalAffiliation',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('date_created', models.DateTimeField(help_text='The original creation date for the item', auto_now_add=True, db_index=True)),
                ('date_modified', models.DateTimeField(help_text='The last moment when the item was modified.', auto_now=True, db_index=True)),
                ('political_party', models.CharField(max_length=5, choices=[('d', 'Democrat'), ('r', 'Republican'), ('i', 'Independent'), ('g', 'Green'), ('l', 'Libertarian'), ('f', 'Federalist'), ('w', 'Whig'), ('j', 'Jeffersonian Republican')])),
                ('source', models.CharField(blank=True, max_length=5, choices=[('b', 'Ballot'), ('a', 'Appointer'), ('o', 'Other')])),
                ('date_start', models.DateField(null=True, blank=True)),
                ('date_granularity_start', models.CharField(blank=True, max_length=15, choices=[('%Y', 'Year'), ('%Y-%m', 'Month'), ('%Y-%m-%d', 'Day')])),
                ('date_end', models.DateField(null=True, blank=True)),
                ('date_granularity_end', models.CharField(blank=True, max_length=15, choices=[('%Y', 'Year'), ('%Y-%m', 'Month'), ('%Y-%m-%d', 'Day')])),
            ],
        ),
        migrations.CreateModel(
            name='Position',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('position_type', models.CharField(blank=True, max_length=20, null=True, choices=[('Judge', (('act-jud', 'Acting Judge'), ('act-pres-jud', 'Acting Presiding Judge'), ('ass-jud', 'Associate Judge'), ('ass-c-jud', 'Associate Chief Judge'), ('ass-pres-jud', 'Associate Presiding Judge'), ('jud', 'Judge'), ('jus', 'Justice'), ('c-jud', 'Chief Judge'), ('c-jus', 'Chief Justice'), ('pres-jud', 'Presiding Judge'), ('pres-jus', 'Presiding Justice'), ('pres-mag', 'Presiding Magistrate'), ('com', 'Commissioner'), ('com-dep', 'Deputy Commissioner'), ('jud-pt', 'Judge Pro Tem'), ('jus-pt', 'Justice Pro Tem'), ('mag-pt', 'Magistrate Pro Tem'), ('ref-jud-tr', 'Judge Trial Referee'), ('ref-off', 'Official Referee'), ('ref-state-trial', 'State Trial Referee'), ('ret-act-jus', 'Active Retired Justice'), ('ret-ass-jud', 'Retired Associate Judge'), ('ret-c-jud', 'Retired Chief Judge'), ('ret-jus', 'Retired Justice'), ('ret-senior-jud', 'Senior Judge'), ('spec-chair', 'Special Chairman'), ('spec-jud', 'Special Judge'), ('spec-m', 'Special Master'), ('spec-scjcbc', 'Special Superior Court Judge for Complex Business Cases'), ('chair', 'Chairman'), ('chan', 'Chancellor'), ('mag', 'Magistrate'), ('presi-jud', 'President'), ('res-jud', 'Reserve Judge'), ('trial-jud', 'Trial Judge'), ('vice-chan', 'Vice Chancellor'), ('vice-cj', 'Vice Chief Judge'))), ('Attorney General', (('att-gen', 'Attorney General'), ('att-gen-ass', 'Assistant Attorney General'), ('att-gen-ass-spec', 'Special Assistant Attorney General'), ('sen-counsel', 'Senior Counsel'), ('dep-sol-gen', 'Deputy Solicitor General'))), ('Appointing Authority', (('pres', 'President'), ('gov', 'Governor'))), ('Clerkships', (('clerk', 'Clerk'), ('staff-atty', 'Staff Attorney'))), ('prof', 'Professor'), ('prac', 'Practitioner'), ('pros', 'Prosecutor'), ('pub_def', 'Public Defender'), ('legis', 'Legislator')])),
                ('job_title', models.CharField(help_text="If title isn't in list, type here.", max_length=100, blank=True)),
                ('organization_name', models.CharField(help_text='If org isnt court or school, type here.', max_length=120, null=True, blank=True)),
                ('date_created', models.DateTimeField(help_text='The time when this item was created', auto_now_add=True, db_index=True)),
                ('date_modified', models.DateTimeField(help_text='The last moment when the item was modified.', auto_now=True, db_index=True)),
                ('date_nominated', models.DateField(help_text='The date recorded in the Senate Executive Journal when a federal judge was nominated for their position or the date a state judge nominated by the legislature. When a nomination is by primary election, this is the date of the election. When a nomination is from a merit commission, this is the date the nomination was announced.', null=True, db_index=True, blank=True)),
                ('date_elected', models.DateField(help_text='Judges are elected in most states. This is the date of theirfirst election. This field will be null if the judge was initially selected by nomination.', null=True, db_index=True, blank=True)),
                ('date_recess_appointment', models.DateField(help_text='If a judge was appointed while congress was in recess, this is the date of that appointment.', null=True, db_index=True, blank=True)),
                ('date_referred_to_judicial_committee', models.DateField(help_text='Federal judges are usually referred to the Judicial Committee before being nominated. This is the date of that referral.', null=True, db_index=True, blank=True)),
                ('date_judicial_committee_action', models.DateField(help_text='The date that the Judicial Committee took action on the referral.', null=True, db_index=True, blank=True)),
                ('date_hearing', models.DateField(help_text='After being nominated, a judge is usually subject to a hearing. This is the date of that hearing.', null=True, db_index=True, blank=True)),
                ('date_confirmation', models.DateField(help_text='After the hearing the senate will vote on judges. This is the date of that vote.', null=True, db_index=True, blank=True)),
                ('date_start', models.DateField(help_text='The date the position starts active duty.', db_index=True)),
                ('date_granularity_start', models.CharField(max_length=15, choices=[('%Y', 'Year'), ('%Y-%m', 'Month'), ('%Y-%m-%d', 'Day')])),
                ('date_retirement', models.DateField(db_index=True, null=True, blank=True)),
                ('date_termination', models.DateField(db_index=True, null=True, blank=True)),
                ('date_granularity_termination', models.CharField(blank=True, max_length=15, choices=[('%Y', 'Year'), ('%Y-%m', 'Month'), ('%Y-%m-%d', 'Day')])),
                ('judicial_committee_action', models.CharField(blank=True, max_length=20, choices=[('no_rep', 'Not Reported'), ('rep_w_rec', 'Reported with Recommendation'), ('rep_wo_rec', 'Reported without Recommendation'), ('rec_postpone', 'Recommendation Postponed'), ('rec_bad', 'Recommended Unfavorably')])),
                ('nomination_process', models.CharField(blank=True, max_length=20, choices=[('fed_senate', 'U.S. Senate'), ('state_senate', 'State Senate'), ('election', 'Primary Election'), ('merit_comm', 'Merit Commission')])),
                ('voice_vote', models.NullBooleanField()),
                ('votes_yes', models.PositiveSmallIntegerField(null=True, blank=True)),
                ('votes_no', models.PositiveSmallIntegerField(null=True, blank=True)),
                ('how_selected', models.CharField(blank=True, max_length=20, choices=[('e_part', 'Partisan Election'), ('e_non_part', 'Non-Partisan Election'), ('a_pres', 'Appointment (President)'), ('a_gov', 'Appointment (Governor)'), ('a_legis', 'Appointment (Legislature)')])),
                ('termination_reason', models.CharField(blank=True, max_length=25, choices=[('ded', 'Death'), ('retire_vol', 'Voluntary Retirement'), ('retire_mand', 'Mandatory Retirement'), ('resign', 'Resigned'), ('other_pos', 'Appointed to Other Judgeship'), ('lost', 'Lost Election'), ('abolished', 'Court Abolished'), ('bad_judge', 'Impeached and Convicted'), ('recess_not_confirmed', 'Recess Appointment Not Confirmed')])),
                ('appointer', models.ForeignKey(related_name='appointed_positions', blank=True, to='people_db.Person', help_text='If this is an appointed position, the person responsible for the appointing.', null=True,
                                                on_delete=models.CASCADE)),
            ],
        ),
        migrations.CreateModel(
            name='Race',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('race', models.CharField(max_length=5, choices=[('w', 'White'), ('b', 'Black or African American'), ('i', 'American Indian or Alaska Native'), ('a', 'Asian'), ('p', 'Native Hawaiian or Other Pacific Islander'), ('h', 'Hispanic/Latino')])),
            ],
        ),
        migrations.CreateModel(
            name='RetentionEvent',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('date_created', models.DateTimeField(help_text='The original creation date for the item', auto_now_add=True, db_index=True)),
                ('date_modified', models.DateTimeField(help_text='The last moment when the item was modified.', auto_now=True, db_index=True)),
                ('retention_type', models.CharField(max_length=10, choices=[('reapp_gov', 'Governor Reappointment'), ('reapp_leg', 'Legislative Reappointment'), ('elec_p', 'Partisan Election'), ('elec_n', 'Nonpartisan Election'), ('elec_u', 'Uncontested Election')])),
                ('date_retention', models.DateField(db_index=True)),
                ('votes_yes', models.PositiveSmallIntegerField(null=True, blank=True)),
                ('votes_no', models.PositiveSmallIntegerField(null=True, blank=True)),
                ('unopposed', models.NullBooleanField()),
                ('won', models.NullBooleanField()),
                ('position', models.ForeignKey(related_name='retention_events', blank=True, to='people_db.Position', null=True,
                                               on_delete=models.CASCADE)),
            ],
        ),
        migrations.CreateModel(
            name='School',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('date_created', models.DateTimeField(help_text='The original creation date for the item', auto_now_add=True, db_index=True)),
                ('date_modified', models.DateTimeField(help_text='The last moment when the item was modified', auto_now=True, db_index=True)),
                ('name', models.CharField(max_length=120, db_index=True)),
                ('ein', models.IntegerField(help_text='The EIN assigned by the IRS', null=True, db_index=True, blank=True)),
                ('is_alias_of', models.ForeignKey(blank=True, to='people_db.School', null=True,
                                                  on_delete=models.CASCADE)),
            ],
        ),
        migrations.CreateModel(
            name='Source',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('date_created', models.DateTimeField(help_text='The original creation date for the item', auto_now_add=True, db_index=True)),
                ('date_modified', models.DateTimeField(help_text='The last moment when the item was modified', auto_now=True, db_index=True)),
                ('url', models.URLField(help_text='The URL where this data was gathered.', max_length=2000, blank=True)),
                ('date_accessed', models.DateField(help_text='The date the data was gathered.', null=True, blank=True)),
                ('notes', models.TextField(help_text="Any additional notes about the data's provenance, in Markdown format.", blank=True)),
                ('person', models.ForeignKey(related_name='sources', blank=True, to='people_db.Person', null=True,
                                             on_delete=models.CASCADE)),
            ],
        ),
    ]
