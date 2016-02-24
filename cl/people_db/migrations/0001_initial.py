# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import localflavor.us.models


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0011_auto_20151222_1240'),
    ]

    operations = [
        migrations.CreateModel(
            name='ABARating',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('date_created', models.DateTimeField(help_text=b'The original creation date for the item', auto_now_add=True, db_index=True)),
                ('date_modified', models.DateTimeField(help_text=b'The last moment when the item was modified.', auto_now=True, db_index=True)),
                ('date_rated', models.DateField(null=True, blank=True)),
                ('date_granularity_rated', models.CharField(blank=True, max_length=15, choices=[(b'%Y', b'Year'), (b'%Y-%m', b'Month'), (b'%Y-%m-%d', b'Day')])),
                ('rating', models.CharField(max_length=5, choices=[(b'ewq', b'Exceptionally Well Qualified'), (b'wq', b'Well Qualified'), (b'q', b'Qualified'), (b'nq', b'Not Qualified'), (b'nqa', b'Not Qualified By Reason of Age')])),
            ],
        ),
        migrations.CreateModel(
            name='Education',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('date_created', models.DateTimeField(help_text=b'The original creation date for the item', auto_now_add=True, db_index=True)),
                ('date_modified', models.DateTimeField(help_text=b'The last moment when the item was modified.', auto_now=True, db_index=True)),
                ('degree', models.CharField(max_length=100, blank=True)),
                ('degree_year', models.PositiveSmallIntegerField(help_text=b'The year the degree was awarded.', null=True, blank=True)),
            ],
        ),
        migrations.CreateModel(
            name='Person',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('date_created', models.DateTimeField(help_text=b'The original creation date for the item', auto_now_add=True, db_index=True)),
                ('date_modified', models.DateTimeField(help_text=b'The last moment when the item was modified.', auto_now=True, db_index=True)),
                ('fjc_id', models.IntegerField(help_text=b'The ID of a judge as assigned by the Federal Judicial Center.', unique=True, null=True, db_index=True, blank=True)),
                ('slug', models.SlugField(max_length=158)),
                ('name_first', models.CharField(max_length=50)),
                ('name_middle', models.CharField(max_length=50, blank=True)),
                ('name_last', models.CharField(max_length=50, db_index=True)),
                ('name_suffix', models.CharField(blank=True, max_length=5, choices=[(b'jr', b'Jr.'), (b'sr', b'Sr.'), (b'1', b'I'), (b'2', b'II'), (b'3', b'III'), (b'4', b'IV')])),
                ('date_dob', models.DateField(null=True, blank=True)),
                ('date_granularity_dob', models.CharField(blank=True, max_length=15, choices=[(b'%Y', b'Year'), (b'%Y-%m', b'Month'), (b'%Y-%m-%d', b'Day')])),
                ('date_dod', models.DateField(null=True, blank=True)),
                ('date_granularity_dod', models.CharField(blank=True, max_length=15, choices=[(b'%Y', b'Year'), (b'%Y-%m', b'Month'), (b'%Y-%m-%d', b'Day')])),
                ('dob_city', models.CharField(max_length=50, blank=True)),
                ('dob_state', localflavor.us.models.USStateField(blank=True, max_length=2, choices=[(b'AL', b'Alabama'), (b'AK', b'Alaska'), (b'AS', b'American Samoa'), (b'AZ', b'Arizona'), (b'AR', b'Arkansas'), (b'AA', b'Armed Forces Americas'), (b'AE', b'Armed Forces Europe'), (b'AP', b'Armed Forces Pacific'), (b'CA', b'California'), (b'CO', b'Colorado'), (b'CT', b'Connecticut'), (b'DE', b'Delaware'), (b'DC', b'District of Columbia'), (b'FL', b'Florida'), (b'GA', b'Georgia'), (b'GU', b'Guam'), (b'HI', b'Hawaii'), (b'ID', b'Idaho'), (b'IL', b'Illinois'), (b'IN', b'Indiana'), (b'IA', b'Iowa'), (b'KS', b'Kansas'), (b'KY', b'Kentucky'), (b'LA', b'Louisiana'), (b'ME', b'Maine'), (b'MD', b'Maryland'), (b'MA', b'Massachusetts'), (b'MI', b'Michigan'), (b'MN', b'Minnesota'), (b'MS', b'Mississippi'), (b'MO', b'Missouri'), (b'MT', b'Montana'), (b'NE', b'Nebraska'), (b'NV', b'Nevada'), (b'NH', b'New Hampshire'), (b'NJ', b'New Jersey'), (b'NM', b'New Mexico'), (b'NY', b'New York'), (b'NC', b'North Carolina'), (b'ND', b'North Dakota'), (b'MP', b'Northern Mariana Islands'), (b'OH', b'Ohio'), (b'OK', b'Oklahoma'), (b'OR', b'Oregon'), (b'PA', b'Pennsylvania'), (b'PR', b'Puerto Rico'), (b'RI', b'Rhode Island'), (b'SC', b'South Carolina'), (b'SD', b'South Dakota'), (b'TN', b'Tennessee'), (b'TX', b'Texas'), (b'UT', b'Utah'), (b'VT', b'Vermont'), (b'VI', b'Virgin Islands'), (b'VA', b'Virginia'), (b'WA', b'Washington'), (b'WV', b'West Virginia'), (b'WI', b'Wisconsin'), (b'WY', b'Wyoming')])),
                ('dod_city', models.CharField(max_length=50, blank=True)),
                ('dod_state', localflavor.us.models.USStateField(blank=True, max_length=2, choices=[(b'AL', b'Alabama'), (b'AK', b'Alaska'), (b'AS', b'American Samoa'), (b'AZ', b'Arizona'), (b'AR', b'Arkansas'), (b'AA', b'Armed Forces Americas'), (b'AE', b'Armed Forces Europe'), (b'AP', b'Armed Forces Pacific'), (b'CA', b'California'), (b'CO', b'Colorado'), (b'CT', b'Connecticut'), (b'DE', b'Delaware'), (b'DC', b'District of Columbia'), (b'FL', b'Florida'), (b'GA', b'Georgia'), (b'GU', b'Guam'), (b'HI', b'Hawaii'), (b'ID', b'Idaho'), (b'IL', b'Illinois'), (b'IN', b'Indiana'), (b'IA', b'Iowa'), (b'KS', b'Kansas'), (b'KY', b'Kentucky'), (b'LA', b'Louisiana'), (b'ME', b'Maine'), (b'MD', b'Maryland'), (b'MA', b'Massachusetts'), (b'MI', b'Michigan'), (b'MN', b'Minnesota'), (b'MS', b'Mississippi'), (b'MO', b'Missouri'), (b'MT', b'Montana'), (b'NE', b'Nebraska'), (b'NV', b'Nevada'), (b'NH', b'New Hampshire'), (b'NJ', b'New Jersey'), (b'NM', b'New Mexico'), (b'NY', b'New York'), (b'NC', b'North Carolina'), (b'ND', b'North Dakota'), (b'MP', b'Northern Mariana Islands'), (b'OH', b'Ohio'), (b'OK', b'Oklahoma'), (b'OR', b'Oregon'), (b'PA', b'Pennsylvania'), (b'PR', b'Puerto Rico'), (b'RI', b'Rhode Island'), (b'SC', b'South Carolina'), (b'SD', b'South Dakota'), (b'TN', b'Tennessee'), (b'TX', b'Texas'), (b'UT', b'Utah'), (b'VT', b'Vermont'), (b'VI', b'Virgin Islands'), (b'VA', b'Virginia'), (b'WA', b'Washington'), (b'WV', b'West Virginia'), (b'WI', b'Wisconsin'), (b'WY', b'Wyoming')])),
                ('gender', models.CharField(max_length=2, choices=[(b'm', b'Male'), (b'f', b'Female'), (b'o', b'Other')])),
                ('is_alias_of', models.ForeignKey(blank=True, to='people_db.Person', null=True)),
            ],
            options={
                'permissions': (('has_beta_api_access', 'Can access features during beta period.'),),
            },
        ),
        migrations.CreateModel(
            name='PoliticalAffiliation',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('date_created', models.DateTimeField(help_text=b'The original creation date for the item', auto_now_add=True, db_index=True)),
                ('date_modified', models.DateTimeField(help_text=b'The last moment when the item was modified.', auto_now=True, db_index=True)),
                ('political_party', models.CharField(max_length=5, choices=[(b'd', b'Democrat'), (b'r', b'Republican'), (b'i', b'Independent'), (b'g', b'Green'), (b'l', b'Libertarian'), (b'f', b'Federalist'), (b'w', b'Whig'), (b'j', b'Jeffersonian Republican')])),
                ('source', models.CharField(blank=True, max_length=5, choices=[(b'b', b'Ballot'), (b'a', b'Appointer'), (b'o', b'Other')])),
                ('date_start', models.DateField(null=True, blank=True)),
                ('date_granularity_start', models.CharField(blank=True, max_length=15, choices=[(b'%Y', b'Year'), (b'%Y-%m', b'Month'), (b'%Y-%m-%d', b'Day')])),
                ('date_end', models.DateField(null=True, blank=True)),
                ('date_granularity_end', models.CharField(blank=True, max_length=15, choices=[(b'%Y', b'Year'), (b'%Y-%m', b'Month'), (b'%Y-%m-%d', b'Day')])),
                ('person', models.ForeignKey(related_name='political_affiliations', blank=True, to='people_db.Person', null=True)),
            ],
        ),
        migrations.CreateModel(
            name='Position',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('position_type', models.CharField(blank=True, max_length=20, null=True, choices=[(b'Judge', ((b'Acting', ((b'act-jud', b'Acting Judge'), (b'act-pres-jud', b'Acting Presiding Judge'))), (b'Associate', ((b'ass-jud', b'Associate Judge'), (b'ass-c-jud', b'Associate Chief Judge'), (b'ass-pres-jud', b'Associate Presiding Judge'), (b'jud', b'Judge'), (b'jus', b'Justice'))), (b'Chief', ((b'c-jud', b'Chief Judge'), (b'c-jus', b'Chief Justice'), (b'pres-jud', b'Presiding Judge'), (b'pres-jus', b'Presiding Justice'), (b'pres-mag', b'Presiding Magistrate'))), (b'Commissioner', ((b'com', b'Commissioner'), (b'com-dep', b'Deputy Commissioner'))), (b'Pro Tem', ((b'jud-pt', b'Judge Pro Tem'), (b'jus-pt', b'Justice Pro Tem'), (b'mag-pt', b'Magistrate Pro Tem'))), (b'Referee', ((b'ref-jud-tr', b'Judge Trial Referee'), (b'ref-off', b'Official Referee'), (b'ref-state-trial', b'State Trial Referee'))), (b'Retired', ((b'ret-act-jus', b'Active Retired Justice'), (b'ret-ass-jud', b'Retired Associate Judge'), (b'ret-c-jud', b'Retired Chief Judge'), (b'ret-jus', b'Retired Justice'), (b'ret-senior-jud', b'Senior Judge'))), (b'Special', ((b'spec-chair', b'Special Chairman'), (b'spec-jud', b'Special Judge'), (b'spec-m', b'Special Master'), (b'spec-scjcbc', b'Special Superior Court Judge for Complex Business Cases'))), (b'Other', ((b'chair', b'Chairman'), (b'chan', b'Chancellor'), (b'mag', b'Magistrate'), (b'presi-jud', b'President'), (b'res-jud', b'Reserve Judge'), (b'trial-jud', b'Trial Judge'), (b'vice-chan', b'Vice Chancellor'), (b'vice-cj', b'Vice Chief Judge'))))), (b'Attorney General', ((b'att-gen', b'Attorney General'), (b'att-gen-ass', b'Assistant Attorney General'), (b'att-gen-ass-spec', b'Special Assistant Attorney General'), (b'sen-counsel', b'Senior Counsel'), (b'dep-sol-gen', b'Deputy Solicitor General'))), (b'Appointing Authority', ((b'pres', b'President'), (b'gov', b'Governor'))), (b'Clerkships', ((b'clerk', b'Clerk'), (b'staff-atty', b'Staff Attorney'))), (b'prof', b'Professor'), (b'prac', b'Practitioner'), (b'pros', b'Prosecutor'), (b'pub_def', b'Public Defender'), (b'legis', b'Legislator')])),
                ('job_title', models.CharField(help_text=b'If title isnt in list, type here.', max_length=100, blank=True)),
                ('organization_name', models.CharField(help_text=b'If org isnt court or school, type here.', max_length=120, null=True, blank=True)),
                ('date_created', models.DateTimeField(help_text=b'The time when this item was created', auto_now_add=True, db_index=True)),
                ('date_modified', models.DateTimeField(help_text=b'The last moment when the item was modified.', auto_now=True, db_index=True)),
                ('date_nominated', models.DateField(help_text=b'The date recorded in the Senate Executive Journal when a federal judge was nominated for their position or the date a state judge nominated by the legislature. When a nomination is by primary election, this is the date of the election. When a nomination is from a merit commission, this is the date the nomination was announced.', null=True, db_index=True, blank=True)),
                ('date_elected', models.DateField(help_text=b'Judges are elected in most states. This is the date of theirfirst election. This field will be null if the judge was initially selected by nomination.', null=True, db_index=True, blank=True)),
                ('date_recess_appointment', models.DateField(help_text=b'If a judge was appointed while congress was in recess, this is the date of that appointment.', null=True, db_index=True, blank=True)),
                ('date_referred_to_judicial_committee', models.DateField(help_text=b'Federal judges are usually referred to the Judicial Committee before being nominated. This is the date of that referral.', null=True, db_index=True, blank=True)),
                ('date_judicial_committee_action', models.DateField(help_text=b'The date that the Judicial Committee took action on the referral.', null=True, db_index=True, blank=True)),
                ('date_hearing', models.DateField(help_text=b'After being nominated, a judge is usually subject to a hearing. This is the date of that hearing.', null=True, db_index=True, blank=True)),
                ('date_confirmation', models.DateField(help_text=b'After the hearing the senate will vote on judges. This is the date of that vote.', null=True, db_index=True, blank=True)),
                ('date_start', models.DateField(help_text=b'The date the position starts active duty.', db_index=True)),
                ('date_granularity_start', models.CharField(max_length=15, choices=[(b'%Y', b'Year'), (b'%Y-%m', b'Month'), (b'%Y-%m-%d', b'Day')])),
                ('date_retirement', models.DateField(db_index=True, null=True, blank=True)),
                ('date_termination', models.DateField(db_index=True, null=True, blank=True)),
                ('date_granularity_termination', models.CharField(blank=True, max_length=15, choices=[(b'%Y', b'Year'), (b'%Y-%m', b'Month'), (b'%Y-%m-%d', b'Day')])),
                ('judicial_committee_action', models.CharField(blank=True, max_length=20, choices=[(b'no_rep', b'Not Reported'), (b'rep_w_rec', b'Reported with Recommendation'), (b'rep_wo_rec', b'Reported without Recommendation'), (b'rec_postpone', b'Recommendation Postponed'), (b'rec_bad', b'Recommended Unfavorably')])),
                ('nomination_process', models.CharField(blank=True, max_length=20, choices=[(b'fed_senate', b'U.S. Senate'), (b'state_senate', b'State Senate'), (b'election', b'Primary Election'), (b'merit_comm', b'Merit Commission')])),
                ('voice_vote', models.NullBooleanField()),
                ('votes_yes', models.PositiveSmallIntegerField(null=True, blank=True)),
                ('votes_no', models.PositiveSmallIntegerField(null=True, blank=True)),
                ('how_selected', models.CharField(max_length=20, choices=[(b'e_part', b'Partisan Election'), (b'e_non_part', b'Non-Partisan Election'), (b'a_pres', b'Appointment (President)'), (b'a_gov', b'Appointment (Governor)'), (b'a_legis', b'Appointment (Legislature)')])),
                ('termination_reason', models.CharField(blank=True, max_length=25, choices=[(b'ded', b'Death'), (b'retire_vol', b'Voluntary Retirement'), (b'retire_mand', b'Mandatory Retirement'), (b'resign', b'Resigned'), (b'other_pos', b'Appointed to Other Judgeship'), (b'lost', b'Lost Election'), (b'abolished', b'Court Abolished'), (b'bad_judge', b'Impeached and Convicted'), (b'recess_not_confirmed', b'Recess Appointment Not Confirmed')])),
                ('court', models.ForeignKey(related_name='court_positions', blank=True, to='search.Court', null=True)),
                ('person', models.ForeignKey(related_name='positions', blank=True, to='people_db.Person', null=True)),
            ],
        ),
        migrations.CreateModel(
            name='Race',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('race', models.CharField(max_length=5, choices=[(b'w', b'White'), (b'b', b'Black or African American'), (b'i', b'American Indian or Alaska Native'), (b'a', b'Asian'), (b'p', b'Native Hawaiian or Other Pacific Islander'), (b'h', b'Hispanic/Latino')])),
            ],
        ),
        migrations.CreateModel(
            name='RetentionEvent',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('date_created', models.DateTimeField(help_text=b'The original creation date for the item', auto_now_add=True, db_index=True)),
                ('date_modified', models.DateTimeField(help_text=b'The last moment when the item was modified.', auto_now=True, db_index=True)),
                ('retention_type', models.CharField(max_length=10, choices=[(b'reapp_gov', b'Governor Reappointment'), (b'reapp_leg', b'Legislative Reappointment'), (b'elec_p', b'Partisan Election'), (b'elec_n', b'Nonpartisan Election'), (b'elec_u', b'Uncontested Election')])),
                ('date_retention', models.DateField(db_index=True)),
                ('votes_yes', models.PositiveSmallIntegerField(null=True, blank=True)),
                ('votes_no', models.PositiveSmallIntegerField(null=True, blank=True)),
                ('unopposed', models.NullBooleanField()),
                ('won', models.NullBooleanField()),
                ('position', models.ForeignKey(related_name='retention_events', blank=True, to='people_db.Position', null=True)),
            ],
        ),
        migrations.CreateModel(
            name='School',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('date_created', models.DateTimeField(help_text=b'The original creation date for the item', auto_now_add=True, db_index=True)),
                ('date_modified', models.DateTimeField(help_text=b'The last moment when the item was modified', auto_now=True, db_index=True)),
                ('name', models.CharField(max_length=120, db_index=True)),
                ('unit_id', models.IntegerField(help_text=b'This is the ID assigned by the Department of Education, as found in the data on their API.', unique=True, null=True, db_index=True)),
                ('ein', models.IntegerField(help_text=b'The EIN assigned by the IRS', null=True, db_index=True, blank=True)),
                ('ope_id', models.IntegerField(help_text=b"This is the ID assigned by the Department of Education's Office of Postsecondary Education (OPE) for schools that have a Program Participation Agreement making them eligible for aid from the Federal Student Financial Assistance Program", null=True, db_index=True, blank=True)),
                ('is_alias_of', models.ForeignKey(blank=True, to='people_db.School', null=True)),
            ],
        ),
        migrations.CreateModel(
            name='Source',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('date_modified', models.DateTimeField(help_text=b'The last moment when the item was modified', auto_now=True, db_index=True)),
                ('url', models.URLField(help_text=b'The URL where this data was gathered.', max_length=2000, blank=True)),
                ('date_accessed', models.DateField(help_text=b'The date the data was gathered.', null=True, blank=True)),
                ('notes', models.TextField(help_text=b"Any additional notes about the data's provenance, in Markdown format.", blank=True)),
                ('person', models.ForeignKey(related_name='sources', blank=True, to='people_db.Person', null=True)),
            ],
        ),
        migrations.AddField(
            model_name='position',
            name='school',
            field=models.ForeignKey(blank=True, to='people_db.School', help_text=b'If academic job, the school where they work.', null=True),
        ),
        migrations.AddField(
            model_name='person',
            name='race',
            field=models.ManyToManyField(to='people_db.Race', blank=True),
        ),
        migrations.AddField(
            model_name='education',
            name='person',
            field=models.ForeignKey(related_name='educations', blank=True, to='people_db.Person', null=True),
        ),
        migrations.AddField(
            model_name='education',
            name='school',
            field=models.ForeignKey(related_name='educations', to='people_db.School'),
        ),
        migrations.AddField(
            model_name='abarating',
            name='person',
            field=models.ForeignKey(related_name='aba_ratings', blank=True, to='people_db.Person', null=True),
        ),
    ]
