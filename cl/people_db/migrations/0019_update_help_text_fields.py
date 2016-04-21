# -*- coding: utf-8 -*-
from __future__ import unicode_literals

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
            field=models.ForeignKey(related_name='aba_ratings', blank=True, to='people_db.Person', help_text=b'The person rated by the American Bar Association', null=True),
        ),
        migrations.AlterField(
            model_name='abarating',
            name='rating',
            field=models.CharField(help_text=b'The rating given to the person.', max_length=5, choices=[(b'ewq', b'Exceptionally Well Qualified'), (b'wq', b'Well Qualified'), (b'q', b'Qualified'), (b'nq', b'Not Qualified'), (b'nqa', b'Not Qualified By Reason of Age')]),
        ),
        migrations.AlterField(
            model_name='education',
            name='person',
            field=models.ForeignKey(related_name='educations', blank=True, to='people_db.Person', help_text=b'The person that completed this education', null=True),
        ),
        migrations.AlterField(
            model_name='education',
            name='school',
            field=models.ForeignKey(related_name='educations', to='people_db.School', help_text=b'The school where this education was compeleted'),
        ),
        migrations.AlterField(
            model_name='person',
            name='date_dob',
            field=models.DateField(help_text=b'The date of birth for the person', null=True, blank=True),
        ),
        migrations.AlterField(
            model_name='person',
            name='date_dod',
            field=models.DateField(help_text=b'The date of death for the person', null=True, blank=True),
        ),
        migrations.AlterField(
            model_name='person',
            name='dob_city',
            field=models.CharField(help_text=b'The city where the person was born.', max_length=50, blank=True),
        ),
        migrations.AlterField(
            model_name='person',
            name='dob_state',
            field=localflavor.us.models.USStateField(blank=True, help_text=b'The state where the person was born.', max_length=2, choices=[(b'AL', b'Alabama'), (b'AK', b'Alaska'), (b'AS', b'American Samoa'), (b'AZ', b'Arizona'), (b'AR', b'Arkansas'), (b'AA', b'Armed Forces Americas'), (b'AE', b'Armed Forces Europe'), (b'AP', b'Armed Forces Pacific'), (b'CA', b'California'), (b'CO', b'Colorado'), (b'CT', b'Connecticut'), (b'DE', b'Delaware'), (b'DC', b'District of Columbia'), (b'FL', b'Florida'), (b'GA', b'Georgia'), (b'GU', b'Guam'), (b'HI', b'Hawaii'), (b'ID', b'Idaho'), (b'IL', b'Illinois'), (b'IN', b'Indiana'), (b'IA', b'Iowa'), (b'KS', b'Kansas'), (b'KY', b'Kentucky'), (b'LA', b'Louisiana'), (b'ME', b'Maine'), (b'MD', b'Maryland'), (b'MA', b'Massachusetts'), (b'MI', b'Michigan'), (b'MN', b'Minnesota'), (b'MS', b'Mississippi'), (b'MO', b'Missouri'), (b'MT', b'Montana'), (b'NE', b'Nebraska'), (b'NV', b'Nevada'), (b'NH', b'New Hampshire'), (b'NJ', b'New Jersey'), (b'NM', b'New Mexico'), (b'NY', b'New York'), (b'NC', b'North Carolina'), (b'ND', b'North Dakota'), (b'MP', b'Northern Mariana Islands'), (b'OH', b'Ohio'), (b'OK', b'Oklahoma'), (b'OR', b'Oregon'), (b'PA', b'Pennsylvania'), (b'PR', b'Puerto Rico'), (b'RI', b'Rhode Island'), (b'SC', b'South Carolina'), (b'SD', b'South Dakota'), (b'TN', b'Tennessee'), (b'TX', b'Texas'), (b'UT', b'Utah'), (b'VT', b'Vermont'), (b'VI', b'Virgin Islands'), (b'VA', b'Virginia'), (b'WA', b'Washington'), (b'WV', b'West Virginia'), (b'WI', b'Wisconsin'), (b'WY', b'Wyoming')]),
        ),
        migrations.AlterField(
            model_name='person',
            name='dod_city',
            field=models.CharField(help_text=b'The city where the person died.', max_length=50, blank=True),
        ),
        migrations.AlterField(
            model_name='person',
            name='dod_state',
            field=localflavor.us.models.USStateField(blank=True, help_text=b'The state where the person died.', max_length=2, choices=[(b'AL', b'Alabama'), (b'AK', b'Alaska'), (b'AS', b'American Samoa'), (b'AZ', b'Arizona'), (b'AR', b'Arkansas'), (b'AA', b'Armed Forces Americas'), (b'AE', b'Armed Forces Europe'), (b'AP', b'Armed Forces Pacific'), (b'CA', b'California'), (b'CO', b'Colorado'), (b'CT', b'Connecticut'), (b'DE', b'Delaware'), (b'DC', b'District of Columbia'), (b'FL', b'Florida'), (b'GA', b'Georgia'), (b'GU', b'Guam'), (b'HI', b'Hawaii'), (b'ID', b'Idaho'), (b'IL', b'Illinois'), (b'IN', b'Indiana'), (b'IA', b'Iowa'), (b'KS', b'Kansas'), (b'KY', b'Kentucky'), (b'LA', b'Louisiana'), (b'ME', b'Maine'), (b'MD', b'Maryland'), (b'MA', b'Massachusetts'), (b'MI', b'Michigan'), (b'MN', b'Minnesota'), (b'MS', b'Mississippi'), (b'MO', b'Missouri'), (b'MT', b'Montana'), (b'NE', b'Nebraska'), (b'NV', b'Nevada'), (b'NH', b'New Hampshire'), (b'NJ', b'New Jersey'), (b'NM', b'New Mexico'), (b'NY', b'New York'), (b'NC', b'North Carolina'), (b'ND', b'North Dakota'), (b'MP', b'Northern Mariana Islands'), (b'OH', b'Ohio'), (b'OK', b'Oklahoma'), (b'OR', b'Oregon'), (b'PA', b'Pennsylvania'), (b'PR', b'Puerto Rico'), (b'RI', b'Rhode Island'), (b'SC', b'South Carolina'), (b'SD', b'South Dakota'), (b'TN', b'Tennessee'), (b'TX', b'Texas'), (b'UT', b'Utah'), (b'VT', b'Vermont'), (b'VI', b'Virgin Islands'), (b'VA', b'Virginia'), (b'WA', b'Washington'), (b'WV', b'West Virginia'), (b'WI', b'Wisconsin'), (b'WY', b'Wyoming')]),
        ),
        migrations.AlterField(
            model_name='person',
            name='gender',
            field=models.CharField(blank=True, help_text=b"The person's gender", max_length=2, choices=[(b'm', b'Male'), (b'f', b'Female'), (b'o', b'Other')]),
        ),
        migrations.AlterField(
            model_name='person',
            name='is_alias_of',
            field=models.ForeignKey(related_name='aliases', blank=True, to='people_db.Person', help_text=b'Any nicknames or other aliases that a person has. For example, William Jefferson Clinton has an alias to Bill', null=True),
        ),
        migrations.AlterField(
            model_name='person',
            name='name_first',
            field=models.CharField(help_text=b'The first name of this person.', max_length=50),
        ),
        migrations.AlterField(
            model_name='person',
            name='name_last',
            field=models.CharField(help_text=b'The last name of this person', max_length=50, db_index=True),
        ),
        migrations.AlterField(
            model_name='person',
            name='name_middle',
            field=models.CharField(help_text=b'The middle name or names of this person', max_length=50, blank=True),
        ),
        migrations.AlterField(
            model_name='person',
            name='name_suffix',
            field=models.CharField(blank=True, help_text=b"Any suffixes that this person's name may have", max_length=5, choices=[(b'jr', b'Jr.'), (b'sr', b'Sr.'), (b'1', b'I'), (b'2', b'II'), (b'3', b'III'), (b'4', b'IV')]),
        ),
        migrations.AlterField(
            model_name='person',
            name='race',
            field=models.ManyToManyField(help_text=b"A person's race or races if they are multi-racial.", to='people_db.Race', blank=True),
        ),
        migrations.AlterField(
            model_name='person',
            name='religion',
            field=models.CharField(help_text=b'The religion of a person', max_length=30, blank=True),
        ),
        migrations.AlterField(
            model_name='person',
            name='slug',
            field=models.SlugField(help_text=b'A generated path for this item as used in CourtListener URLs', max_length=158),
        ),
        migrations.AlterField(
            model_name='politicalaffiliation',
            name='date_end',
            field=models.DateField(help_text=b'The date the affiliation ended.', null=True, blank=True),
        ),
        migrations.AlterField(
            model_name='politicalaffiliation',
            name='date_start',
            field=models.DateField(help_text=b'The date the political affiliation was first documented', null=True, blank=True),
        ),
        migrations.AlterField(
            model_name='politicalaffiliation',
            name='person',
            field=models.ForeignKey(related_name='political_affiliations', blank=True, to='people_db.Person', help_text=b'The person with the political affiliation', null=True),
        ),
        migrations.AlterField(
            model_name='politicalaffiliation',
            name='political_party',
            field=models.CharField(help_text=b'The political party the person is affiliated with.', max_length=5, choices=[(b'd', b'Democrat'), (b'r', b'Republican'), (b'i', b'Independent'), (b'g', b'Green'), (b'l', b'Libertarian'), (b'f', b'Federalist'), (b'w', b'Whig'), (b'j', b'Jeffersonian Republican'), (b'u', b'National Union')]),
        ),
        migrations.AlterField(
            model_name='politicalaffiliation',
            name='source',
            field=models.CharField(blank=True, help_text=b'The source of the political affiliation -- where it is documented that this affiliation exists.', max_length=5, choices=[(b'b', b'Ballot'), (b'a', b'Appointer'), (b'o', b'Other')]),
        ),
        migrations.AlterField(
            model_name='position',
            name='appointer',
            field=models.ForeignKey(related_name='appointed_positions', blank=True, to='people_db.Position', help_text=b'If this is an appointed position, the person-position responsible for the appointment. This field references other positions instead of referencing people because that allows you to know the position a person held when an appointment was made.', null=True),
        ),
        migrations.AlterField(
            model_name='position',
            name='court',
            field=models.ForeignKey(related_name='court_positions', blank=True, to='search.Court', help_text=b'If this was a judicial position, this is the jurisdiction where it was held.', null=True),
        ),
        migrations.AlterField(
            model_name='position',
            name='how_selected',
            field=models.CharField(blank=True, help_text=b'The method that was used for selecting this judge for this position (generally an election or appointment).', max_length=20, choices=[(b'Election', ((b'e_part', b'Partisan Election'), (b'e_non_part', b'Non-Partisan Election'))), (b'Appointment', ((b'a_pres', b'Appointment (President)'), (b'a_gov', b'Appointment (Governor)'), (b'a_legis', b'Appointment (Legislature)')))]),
        ),
        migrations.AlterField(
            model_name='position',
            name='job_title',
            field=models.CharField(help_text=b"If title isn't in position_type, a free-text position may be entered here.", max_length=100, blank=True),
        ),
        migrations.AlterField(
            model_name='position',
            name='judicial_committee_action',
            field=models.CharField(blank=True, help_text=b'The action that the judicial committee took in response to a nomination', max_length=20, choices=[(b'no_rep', b'Not Reported'), (b'rep_w_rec', b'Reported with Recommendation'), (b'rep_wo_rec', b'Reported without Recommendation'), (b'rec_postpone', b'Recommendation Postponed'), (b'rec_bad', b'Recommended Unfavorably')]),
        ),
        migrations.AlterField(
            model_name='position',
            name='nomination_process',
            field=models.CharField(blank=True, help_text=b'The process by which a person was nominated into this position.', max_length=20, choices=[(b'fed_senate', b'U.S. Senate'), (b'state_senate', b'State Senate'), (b'election', b'Primary Election'), (b'merit_comm', b'Merit Commission')]),
        ),
        migrations.AlterField(
            model_name='position',
            name='organization_name',
            field=models.CharField(help_text=b'If the organization where this position was held is not a school or court, this is the place it was held.', max_length=120, null=True, blank=True),
        ),
        migrations.AlterField(
            model_name='position',
            name='person',
            field=models.ForeignKey(related_name='positions', blank=True, to='people_db.Person', help_text=b'The person that held the position.', null=True),
        ),
        migrations.AlterField(
            model_name='position',
            name='position_type',
            field=models.CharField(blank=True, max_length=20, null=True, help_text=b'If this is a judicial position, this indicates the role the person had. This field may be blank if job_title is complete instead.', choices=[(b'Judge', ((b'act-jud', b'Acting Judge'), (b'act-pres-jud', b'Acting Presiding Judge'), (b'ass-jud', b'Associate Judge'), (b'ass-c-jud', b'Associate Chief Judge'), (b'ass-pres-jud', b'Associate Presiding Judge'), (b'jud', b'Judge'), (b'jus', b'Justice'), (b'c-jud', b'Chief Judge'), (b'c-jus', b'Chief Justice'), (b'pres-jud', b'Presiding Judge'), (b'pres-jus', b'Presiding Justice'), (b'pres-mag', b'Presiding Magistrate'), (b'com', b'Commissioner'), (b'com-dep', b'Deputy Commissioner'), (b'jud-pt', b'Judge Pro Tem'), (b'jus-pt', b'Justice Pro Tem'), (b'mag-pt', b'Magistrate Pro Tem'), (b'ref-jud-tr', b'Judge Trial Referee'), (b'ref-off', b'Official Referee'), (b'ref-state-trial', b'State Trial Referee'), (b'ret-act-jus', b'Active Retired Justice'), (b'ret-ass-jud', b'Retired Associate Judge'), (b'ret-c-jud', b'Retired Chief Judge'), (b'ret-jus', b'Retired Justice'), (b'ret-senior-jud', b'Senior Judge'), (b'spec-chair', b'Special Chairman'), (b'spec-jud', b'Special Judge'), (b'spec-m', b'Special Master'), (b'spec-scjcbc', b'Special Superior Court Judge for Complex Business Cases'), (b'chair', b'Chairman'), (b'chan', b'Chancellor'), (b'mag', b'Magistrate'), (b'presi-jud', b'President'), (b'res-jud', b'Reserve Judge'), (b'trial-jud', b'Trial Judge'), (b'vice-chan', b'Vice Chancellor'), (b'vice-cj', b'Vice Chief Judge'))), (b'Attorney General', ((b'att-gen', b'Attorney General'), (b'att-gen-ass', b'Assistant Attorney General'), (b'att-gen-ass-spec', b'Special Assistant Attorney General'), (b'sen-counsel', b'Senior Counsel'), (b'dep-sol-gen', b'Deputy Solicitor General'))), (b'Appointing Authority', ((b'pres', b'President of the United States'), (b'gov', b'Governor'))), (b'Clerkships', ((b'clerk', b'Clerk'), (b'staff-atty', b'Staff Attorney'))), (b'prof', b'Professor'), (b'prac', b'Practitioner'), (b'pros', b'Prosecutor'), (b'pub_def', b'Public Defender'), (b'legis', b'Legislator')]),
        ),
        migrations.AlterField(
            model_name='position',
            name='predecessor',
            field=models.ForeignKey(blank=True, to='people_db.Person', help_text=b'The person that previously held this position', null=True),
        ),
        migrations.AlterField(
            model_name='position',
            name='school',
            field=models.ForeignKey(blank=True, to='people_db.School', help_text=b'If this was an academic job, this is the school where the person worked.', null=True),
        ),
        migrations.AlterField(
            model_name='position',
            name='termination_reason',
            field=models.CharField(blank=True, help_text=b'The reason for a termination', max_length=25, choices=[(b'ded', b'Death'), (b'retire_vol', b'Voluntary Retirement'), (b'retire_mand', b'Mandatory Retirement'), (b'resign', b'Resigned'), (b'other_pos', b'Appointed to Other Judgeship'), (b'lost', b'Lost Election'), (b'abolished', b'Court Abolished'), (b'bad_judge', b'Impeached and Convicted'), (b'recess_not_confirmed', b'Recess Appointment Not Confirmed')]),
        ),
        migrations.AlterField(
            model_name='position',
            name='voice_vote',
            field=models.NullBooleanField(help_text=b'Whether the Senate voted by voice vote for this position.'),
        ),
        migrations.AlterField(
            model_name='position',
            name='vote_type',
            field=models.CharField(blank=True, help_text=b'The type of vote that resulted in this position.', max_length=2, choices=[(b's', b'Senate'), (b'p', b'Partisan Election'), (b'np', b'Non-Partisan Election')]),
        ),
        migrations.AlterField(
            model_name='position',
            name='votes_no',
            field=models.PositiveIntegerField(help_text=b'If votes are an integer, this is the number of votes opposed to a position.', null=True, blank=True),
        ),
        migrations.AlterField(
            model_name='position',
            name='votes_no_percent',
            field=models.FloatField(help_text=b'If votes are a percentage, this is the percentage of votes opposed to a position.', null=True, blank=True),
        ),
        migrations.AlterField(
            model_name='position',
            name='votes_yes',
            field=models.PositiveIntegerField(help_text=b'If votes are an integer, this is the number of votes in favor of a position.', null=True, blank=True),
        ),
        migrations.AlterField(
            model_name='position',
            name='votes_yes_percent',
            field=models.FloatField(help_text=b'If votes are a percentage, this is the percentage of votes in favor of a position.', null=True, blank=True),
        ),
        migrations.AlterField(
            model_name='retentionevent',
            name='date_retention',
            field=models.DateField(help_text=b'The date of retention', db_index=True),
        ),
        migrations.AlterField(
            model_name='retentionevent',
            name='position',
            field=models.ForeignKey(related_name='retention_events', blank=True, to='people_db.Position', help_text=b'The position that was retained by this event.', null=True),
        ),
        migrations.AlterField(
            model_name='retentionevent',
            name='retention_type',
            field=models.CharField(help_text=b'The method through which this position was retained.', max_length=10, choices=[(b'reapp_gov', b'Governor Reappointment'), (b'reapp_leg', b'Legislative Reappointment'), (b'elec_p', b'Partisan Election'), (b'elec_n', b'Nonpartisan Election'), (b'elec_u', b'Uncontested Election')]),
        ),
        migrations.AlterField(
            model_name='retentionevent',
            name='unopposed',
            field=models.NullBooleanField(help_text=b'Whether the position was unopposed at the time of retention.'),
        ),
        migrations.AlterField(
            model_name='retentionevent',
            name='votes_no',
            field=models.PositiveIntegerField(help_text=b'If votes are an integer, this is the number of votes opposed to a position.', null=True, blank=True),
        ),
        migrations.AlterField(
            model_name='retentionevent',
            name='votes_no_percent',
            field=models.FloatField(help_text=b'If votes are a percentage, this is the percentage of votes opposed to a position.', null=True, blank=True),
        ),
        migrations.AlterField(
            model_name='retentionevent',
            name='votes_yes',
            field=models.PositiveIntegerField(help_text=b'If votes are an integer, this is the number of votes in favor of a position.', null=True, blank=True),
        ),
        migrations.AlterField(
            model_name='retentionevent',
            name='votes_yes_percent',
            field=models.FloatField(help_text=b'If votes are a percentage, this is the percentage of votes in favor of a position.', null=True, blank=True),
        ),
        migrations.AlterField(
            model_name='retentionevent',
            name='won',
            field=models.NullBooleanField(help_text=b'Whether the retention event was won.'),
        ),
        migrations.AlterField(
            model_name='school',
            name='is_alias_of',
            field=models.ForeignKey(blank=True, to='people_db.School', help_text=b'Any alternate names that a school may have', null=True),
        ),
        migrations.AlterField(
            model_name='school',
            name='name',
            field=models.CharField(help_text=b'The name of the school or alias', max_length=120, db_index=True),
        ),
    ]
