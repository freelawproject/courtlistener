# -*- coding: utf-8 -*-


import localflavor.us.models
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('people_db', '0018_auto_20160419_0926'),
    ]

    operations = [
        migrations.AlterField(
            model_name='abarating',
            name='person',
            field=models.ForeignKey(related_name='aba_ratings', blank=True, to='people_db.Person', help_text='The person rated by the American Bar Association', null=True,
                                    on_delete=models.CASCADE),
        ),
        migrations.AlterField(
            model_name='abarating',
            name='rating',
            field=models.CharField(help_text='The rating given to the person.', max_length=5, choices=[('ewq', 'Exceptionally Well Qualified'), ('wq', 'Well Qualified'), ('q', 'Qualified'), ('nq', 'Not Qualified'), ('nqa', 'Not Qualified By Reason of Age')]),
        ),
        migrations.AlterField(
            model_name='education',
            name='person',
            field=models.ForeignKey(related_name='educations', blank=True, to='people_db.Person', help_text='The person that completed this education', null=True,
                                    on_delete=models.CASCADE),
        ),
        migrations.AlterField(
            model_name='education',
            name='school',
            field=models.ForeignKey(related_name='educations', to='people_db.School', help_text='The school where this education was compeleted',
                                    on_delete=models.CASCADE),
        ),
        migrations.AlterField(
            model_name='person',
            name='date_dob',
            field=models.DateField(help_text='The date of birth for the person', null=True, blank=True),
        ),
        migrations.AlterField(
            model_name='person',
            name='date_dod',
            field=models.DateField(help_text='The date of death for the person', null=True, blank=True),
        ),
        migrations.AlterField(
            model_name='person',
            name='dob_city',
            field=models.CharField(help_text='The city where the person was born.', max_length=50, blank=True),
        ),
        migrations.AlterField(
            model_name='person',
            name='dob_state',
            field=localflavor.us.models.USStateField(blank=True, help_text='The state where the person was born.', max_length=2, choices=[('AL', 'Alabama'), ('AK', 'Alaska'), ('AS', 'American Samoa'), ('AZ', 'Arizona'), ('AR', 'Arkansas'), ('AA', 'Armed Forces Americas'), ('AE', 'Armed Forces Europe'), ('AP', 'Armed Forces Pacific'), ('CA', 'California'), ('CO', 'Colorado'), ('CT', 'Connecticut'), ('DE', 'Delaware'), ('DC', 'District of Columbia'), ('FL', 'Florida'), ('GA', 'Georgia'), ('GU', 'Guam'), ('HI', 'Hawaii'), ('ID', 'Idaho'), ('IL', 'Illinois'), ('IN', 'Indiana'), ('IA', 'Iowa'), ('KS', 'Kansas'), ('KY', 'Kentucky'), ('LA', 'Louisiana'), ('ME', 'Maine'), ('MD', 'Maryland'), ('MA', 'Massachusetts'), ('MI', 'Michigan'), ('MN', 'Minnesota'), ('MS', 'Mississippi'), ('MO', 'Missouri'), ('MT', 'Montana'), ('NE', 'Nebraska'), ('NV', 'Nevada'), ('NH', 'New Hampshire'), ('NJ', 'New Jersey'), ('NM', 'New Mexico'), ('NY', 'New York'), ('NC', 'North Carolina'), ('ND', 'North Dakota'), ('MP', 'Northern Mariana Islands'), ('OH', 'Ohio'), ('OK', 'Oklahoma'), ('OR', 'Oregon'), ('PA', 'Pennsylvania'), ('PR', 'Puerto Rico'), ('RI', 'Rhode Island'), ('SC', 'South Carolina'), ('SD', 'South Dakota'), ('TN', 'Tennessee'), ('TX', 'Texas'), ('UT', 'Utah'), ('VT', 'Vermont'), ('VI', 'Virgin Islands'), ('VA', 'Virginia'), ('WA', 'Washington'), ('WV', 'West Virginia'), ('WI', 'Wisconsin'), ('WY', 'Wyoming')]),
        ),
        migrations.AlterField(
            model_name='person',
            name='dod_city',
            field=models.CharField(help_text='The city where the person died.', max_length=50, blank=True),
        ),
        migrations.AlterField(
            model_name='person',
            name='dod_state',
            field=localflavor.us.models.USStateField(blank=True, help_text='The state where the person died.', max_length=2, choices=[('AL', 'Alabama'), ('AK', 'Alaska'), ('AS', 'American Samoa'), ('AZ', 'Arizona'), ('AR', 'Arkansas'), ('AA', 'Armed Forces Americas'), ('AE', 'Armed Forces Europe'), ('AP', 'Armed Forces Pacific'), ('CA', 'California'), ('CO', 'Colorado'), ('CT', 'Connecticut'), ('DE', 'Delaware'), ('DC', 'District of Columbia'), ('FL', 'Florida'), ('GA', 'Georgia'), ('GU', 'Guam'), ('HI', 'Hawaii'), ('ID', 'Idaho'), ('IL', 'Illinois'), ('IN', 'Indiana'), ('IA', 'Iowa'), ('KS', 'Kansas'), ('KY', 'Kentucky'), ('LA', 'Louisiana'), ('ME', 'Maine'), ('MD', 'Maryland'), ('MA', 'Massachusetts'), ('MI', 'Michigan'), ('MN', 'Minnesota'), ('MS', 'Mississippi'), ('MO', 'Missouri'), ('MT', 'Montana'), ('NE', 'Nebraska'), ('NV', 'Nevada'), ('NH', 'New Hampshire'), ('NJ', 'New Jersey'), ('NM', 'New Mexico'), ('NY', 'New York'), ('NC', 'North Carolina'), ('ND', 'North Dakota'), ('MP', 'Northern Mariana Islands'), ('OH', 'Ohio'), ('OK', 'Oklahoma'), ('OR', 'Oregon'), ('PA', 'Pennsylvania'), ('PR', 'Puerto Rico'), ('RI', 'Rhode Island'), ('SC', 'South Carolina'), ('SD', 'South Dakota'), ('TN', 'Tennessee'), ('TX', 'Texas'), ('UT', 'Utah'), ('VT', 'Vermont'), ('VI', 'Virgin Islands'), ('VA', 'Virginia'), ('WA', 'Washington'), ('WV', 'West Virginia'), ('WI', 'Wisconsin'), ('WY', 'Wyoming')]),
        ),
        migrations.AlterField(
            model_name='person',
            name='gender',
            field=models.CharField(blank=True, help_text="The person's gender", max_length=2, choices=[('m', 'Male'), ('f', 'Female'), ('o', 'Other')]),
        ),
        migrations.AlterField(
            model_name='person',
            name='is_alias_of',
            field=models.ForeignKey(related_name='aliases', blank=True, to='people_db.Person', help_text='Any nicknames or other aliases that a person has. For example, William Jefferson Clinton has an alias to Bill', null=True,
                                    on_delete=models.CASCADE),
        ),
        migrations.AlterField(
            model_name='person',
            name='name_first',
            field=models.CharField(help_text='The first name of this person.', max_length=50),
        ),
        migrations.AlterField(
            model_name='person',
            name='name_last',
            field=models.CharField(help_text='The last name of this person', max_length=50, db_index=True),
        ),
        migrations.AlterField(
            model_name='person',
            name='name_middle',
            field=models.CharField(help_text='The middle name or names of this person', max_length=50, blank=True),
        ),
        migrations.AlterField(
            model_name='person',
            name='name_suffix',
            field=models.CharField(blank=True, help_text="Any suffixes that this person's name may have", max_length=5, choices=[('jr', 'Jr.'), ('sr', 'Sr.'), ('1', 'I'), ('2', 'II'), ('3', 'III'), ('4', 'IV')]),
        ),
        migrations.AlterField(
            model_name='person',
            name='race',
            field=models.ManyToManyField(help_text="A person's race or races if they are multi-racial.", to='people_db.Race', blank=True),
        ),
        migrations.AlterField(
            model_name='person',
            name='religion',
            field=models.CharField(help_text='The religion of a person', max_length=30, blank=True),
        ),
        migrations.AlterField(
            model_name='person',
            name='slug',
            field=models.SlugField(help_text='A generated path for this item as used in CourtListener URLs', max_length=158),
        ),
        migrations.AlterField(
            model_name='politicalaffiliation',
            name='date_end',
            field=models.DateField(help_text='The date the affiliation ended.', null=True, blank=True),
        ),
        migrations.AlterField(
            model_name='politicalaffiliation',
            name='date_start',
            field=models.DateField(help_text='The date the political affiliation was first documented', null=True, blank=True),
        ),
        migrations.AlterField(
            model_name='politicalaffiliation',
            name='person',
            field=models.ForeignKey(related_name='political_affiliations', blank=True, to='people_db.Person', help_text='The person with the political affiliation', null=True,
                                    on_delete=models.CASCADE),
        ),
        migrations.AlterField(
            model_name='politicalaffiliation',
            name='political_party',
            field=models.CharField(help_text='The political party the person is affiliated with.', max_length=5, choices=[('d', 'Democrat'), ('r', 'Republican'), ('i', 'Independent'), ('g', 'Green'), ('l', 'Libertarian'), ('f', 'Federalist'), ('w', 'Whig'), ('j', 'Jeffersonian Republican'), ('u', 'National Union')]),
        ),
        migrations.AlterField(
            model_name='politicalaffiliation',
            name='source',
            field=models.CharField(blank=True, help_text='The source of the political affiliation -- where it is documented that this affiliation exists.', max_length=5, choices=[('b', 'Ballot'), ('a', 'Appointer'), ('o', 'Other')]),
        ),
        migrations.AlterField(
            model_name='position',
            name='appointer',
            field=models.ForeignKey(related_name='appointed_positions', blank=True, to='people_db.Position', help_text='If this is an appointed position, the person-position responsible for the appointment. This field references other positions instead of referencing people because that allows you to know the position a person held when an appointment was made.', null=True,
                                    on_delete=models.CASCADE),
        ),
        migrations.AlterField(
            model_name='position',
            name='court',
            field=models.ForeignKey(related_name='court_positions', blank=True, to='search.Court', help_text='If this was a judicial position, this is the jurisdiction where it was held.', null=True,
                                    on_delete=models.CASCADE),
        ),
        migrations.AlterField(
            model_name='position',
            name='how_selected',
            field=models.CharField(blank=True, help_text='The method that was used for selecting this judge for this position (generally an election or appointment).', max_length=20, choices=[('Election', (('e_part', 'Partisan Election'), ('e_non_part', 'Non-Partisan Election'))), ('Appointment', (('a_pres', 'Appointment (President)'), ('a_gov', 'Appointment (Governor)'), ('a_legis', 'Appointment (Legislature)')))]),
        ),
        migrations.AlterField(
            model_name='position',
            name='job_title',
            field=models.CharField(help_text="If title isn't in position_type, a free-text position may be entered here.", max_length=100, blank=True),
        ),
        migrations.AlterField(
            model_name='position',
            name='judicial_committee_action',
            field=models.CharField(blank=True, help_text='The action that the judicial committee took in response to a nomination', max_length=20, choices=[('no_rep', 'Not Reported'), ('rep_w_rec', 'Reported with Recommendation'), ('rep_wo_rec', 'Reported without Recommendation'), ('rec_postpone', 'Recommendation Postponed'), ('rec_bad', 'Recommended Unfavorably')]),
        ),
        migrations.AlterField(
            model_name='position',
            name='nomination_process',
            field=models.CharField(blank=True, help_text='The process by which a person was nominated into this position.', max_length=20, choices=[('fed_senate', 'U.S. Senate'), ('state_senate', 'State Senate'), ('election', 'Primary Election'), ('merit_comm', 'Merit Commission')]),
        ),
        migrations.AlterField(
            model_name='position',
            name='organization_name',
            field=models.CharField(help_text='If the organization where this position was held is not a school or court, this is the place it was held.', max_length=120, null=True, blank=True),
        ),
        migrations.AlterField(
            model_name='position',
            name='person',
            field=models.ForeignKey(related_name='positions', blank=True, to='people_db.Person', help_text='The person that held the position.', null=True,
                                    on_delete=models.CASCADE),
        ),
        migrations.AlterField(
            model_name='position',
            name='position_type',
            field=models.CharField(blank=True, max_length=20, null=True, help_text='If this is a judicial position, this indicates the role the person had. This field may be blank if job_title is complete instead.', choices=[('Judge', (('act-jud', 'Acting Judge'), ('act-pres-jud', 'Acting Presiding Judge'), ('ass-jud', 'Associate Judge'), ('ass-c-jud', 'Associate Chief Judge'), ('ass-pres-jud', 'Associate Presiding Judge'), ('jud', 'Judge'), ('jus', 'Justice'), ('c-jud', 'Chief Judge'), ('c-jus', 'Chief Justice'), ('pres-jud', 'Presiding Judge'), ('pres-jus', 'Presiding Justice'), ('pres-mag', 'Presiding Magistrate'), ('com', 'Commissioner'), ('com-dep', 'Deputy Commissioner'), ('jud-pt', 'Judge Pro Tem'), ('jus-pt', 'Justice Pro Tem'), ('mag-pt', 'Magistrate Pro Tem'), ('ref-jud-tr', 'Judge Trial Referee'), ('ref-off', 'Official Referee'), ('ref-state-trial', 'State Trial Referee'), ('ret-act-jus', 'Active Retired Justice'), ('ret-ass-jud', 'Retired Associate Judge'), ('ret-c-jud', 'Retired Chief Judge'), ('ret-jus', 'Retired Justice'), ('ret-senior-jud', 'Senior Judge'), ('spec-chair', 'Special Chairman'), ('spec-jud', 'Special Judge'), ('spec-m', 'Special Master'), ('spec-scjcbc', 'Special Superior Court Judge for Complex Business Cases'), ('chair', 'Chairman'), ('chan', 'Chancellor'), ('mag', 'Magistrate'), ('presi-jud', 'President'), ('res-jud', 'Reserve Judge'), ('trial-jud', 'Trial Judge'), ('vice-chan', 'Vice Chancellor'), ('vice-cj', 'Vice Chief Judge'))), ('Attorney General', (('att-gen', 'Attorney General'), ('att-gen-ass', 'Assistant Attorney General'), ('att-gen-ass-spec', 'Special Assistant Attorney General'), ('sen-counsel', 'Senior Counsel'), ('dep-sol-gen', 'Deputy Solicitor General'))), ('Appointing Authority', (('pres', 'President of the United States'), ('gov', 'Governor'))), ('Clerkships', (('clerk', 'Clerk'), ('staff-atty', 'Staff Attorney'))), ('prof', 'Professor'), ('prac', 'Practitioner'), ('pros', 'Prosecutor'), ('pub_def', 'Public Defender'), ('legis', 'Legislator')]),
        ),
        migrations.AlterField(
            model_name='position',
            name='predecessor',
            field=models.ForeignKey(blank=True, to='people_db.Person', help_text='The person that previously held this position', null=True,
                                    on_delete=models.CASCADE),
        ),
        migrations.AlterField(
            model_name='position',
            name='school',
            field=models.ForeignKey(blank=True, to='people_db.School', help_text='If this was an academic job, this is the school where the person worked.', null=True,
                                    on_delete=models.CASCADE),
        ),
        migrations.AlterField(
            model_name='position',
            name='termination_reason',
            field=models.CharField(blank=True, help_text='The reason for a termination', max_length=25, choices=[('ded', 'Death'), ('retire_vol', 'Voluntary Retirement'), ('retire_mand', 'Mandatory Retirement'), ('resign', 'Resigned'), ('other_pos', 'Appointed to Other Judgeship'), ('lost', 'Lost Election'), ('abolished', 'Court Abolished'), ('bad_judge', 'Impeached and Convicted'), ('recess_not_confirmed', 'Recess Appointment Not Confirmed')]),
        ),
        migrations.AlterField(
            model_name='position',
            name='voice_vote',
            field=models.NullBooleanField(help_text='Whether the Senate voted by voice vote for this position.'),
        ),
        migrations.AlterField(
            model_name='position',
            name='vote_type',
            field=models.CharField(blank=True, help_text='The type of vote that resulted in this position.', max_length=2, choices=[('s', 'Senate'), ('p', 'Partisan Election'), ('np', 'Non-Partisan Election')]),
        ),
        migrations.AlterField(
            model_name='position',
            name='votes_no',
            field=models.PositiveIntegerField(help_text='If votes are an integer, this is the number of votes opposed to a position.', null=True, blank=True),
        ),
        migrations.AlterField(
            model_name='position',
            name='votes_no_percent',
            field=models.FloatField(help_text='If votes are a percentage, this is the percentage of votes opposed to a position.', null=True, blank=True),
        ),
        migrations.AlterField(
            model_name='position',
            name='votes_yes',
            field=models.PositiveIntegerField(help_text='If votes are an integer, this is the number of votes in favor of a position.', null=True, blank=True),
        ),
        migrations.AlterField(
            model_name='position',
            name='votes_yes_percent',
            field=models.FloatField(help_text='If votes are a percentage, this is the percentage of votes in favor of a position.', null=True, blank=True),
        ),
        migrations.AlterField(
            model_name='retentionevent',
            name='date_retention',
            field=models.DateField(help_text='The date of retention', db_index=True),
        ),
        migrations.AlterField(
            model_name='retentionevent',
            name='position',
            field=models.ForeignKey(related_name='retention_events', blank=True, to='people_db.Position', help_text='The position that was retained by this event.', null=True,
                                    on_delete=models.CASCADE),
        ),
        migrations.AlterField(
            model_name='retentionevent',
            name='retention_type',
            field=models.CharField(help_text='The method through which this position was retained.', max_length=10, choices=[('reapp_gov', 'Governor Reappointment'), ('reapp_leg', 'Legislative Reappointment'), ('elec_p', 'Partisan Election'), ('elec_n', 'Nonpartisan Election'), ('elec_u', 'Uncontested Election')]),
        ),
        migrations.AlterField(
            model_name='retentionevent',
            name='unopposed',
            field=models.NullBooleanField(help_text='Whether the position was unopposed at the time of retention.'),
        ),
        migrations.AlterField(
            model_name='retentionevent',
            name='votes_no',
            field=models.PositiveIntegerField(help_text='If votes are an integer, this is the number of votes opposed to a position.', null=True, blank=True),
        ),
        migrations.AlterField(
            model_name='retentionevent',
            name='votes_no_percent',
            field=models.FloatField(help_text='If votes are a percentage, this is the percentage of votes opposed to a position.', null=True, blank=True),
        ),
        migrations.AlterField(
            model_name='retentionevent',
            name='votes_yes',
            field=models.PositiveIntegerField(help_text='If votes are an integer, this is the number of votes in favor of a position.', null=True, blank=True),
        ),
        migrations.AlterField(
            model_name='retentionevent',
            name='votes_yes_percent',
            field=models.FloatField(help_text='If votes are a percentage, this is the percentage of votes in favor of a position.', null=True, blank=True),
        ),
        migrations.AlterField(
            model_name='retentionevent',
            name='won',
            field=models.NullBooleanField(help_text='Whether the retention event was won.'),
        ),
        migrations.AlterField(
            model_name='school',
            name='is_alias_of',
            field=models.ForeignKey(blank=True, to='people_db.School', help_text='Any alternate names that a school may have', null=True,
                                    on_delete=models.CASCADE),
        ),
        migrations.AlterField(
            model_name='school',
            name='name',
            field=models.CharField(help_text='The name of the school or alias', max_length=120, db_index=True),
        ),
    ]
