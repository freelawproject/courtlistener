# -*- coding: utf-8 -*-


from django.db import migrations, models
import localflavor.us.models


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0044_convert_pacer_document_number'),
        ('people_db', '0023_add_inferred_position_field'),
    ]

    operations = [
        migrations.CreateModel(
            name='Attorney',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('date_created', models.DateTimeField(help_text='The time when this item was created', auto_now_add=True, db_index=True)),
                ('date_modified', models.DateTimeField(help_text='The last moment when the item was modified.', auto_now=True, db_index=True)),
                ('date_sourced', models.DateField(help_text='The latest date on the source docket that populated this information. When information is in conflict use the latest data.', db_index=True)),
                ('name', models.TextField(help_text='The name of the attorney.', db_index=True)),
                ('contact_raw', models.TextField(help_text='The raw contents of the contact field', db_index=True)),
                ('phone', localflavor.us.models.PhoneNumberField(help_text='The phone number of the attorney.', max_length=20)),
                ('fax', localflavor.us.models.PhoneNumberField(help_text='The fax number of the attorney.', max_length=20)),
                ('email', models.EmailField(help_text='The email address of the attorney.', max_length=254)),
            ],
        ),
        migrations.CreateModel(
            name='AttorneyOrganization',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('date_created', models.DateTimeField(help_text='The time when this item was created', auto_now_add=True, db_index=True)),
                ('date_modified', models.DateTimeField(help_text='The last moment when the item was modified.', auto_now=True, db_index=True)),
                ('lookup_key', models.TextField(help_text='A trimmed version of the address for duplicate matching.', unique=True, db_index=True)),
                ('name', models.TextField(help_text='The name of the organization.', db_index=True)),
                ('address1', models.TextField(help_text='The normalized address1 of the organization', db_index=True)),
                ('address2', models.TextField(help_text='The normalized address2 of the organization', db_index=True)),
                ('city', models.TextField(help_text='The normalized city of the organization', db_index=True)),
                ('state', localflavor.us.models.USPostalCodeField(help_text='The two-letter USPS postal abbreviation for the organization', max_length=2, db_index=True, choices=[('AL', 'Alabama'), ('AK', 'Alaska'), ('AS', 'American Samoa'), ('AZ', 'Arizona'), ('AR', 'Arkansas'), ('AA', 'Armed Forces Americas'), ('AE', 'Armed Forces Europe'), ('AP', 'Armed Forces Pacific'), ('CA', 'California'), ('CO', 'Colorado'), ('CT', 'Connecticut'), ('DE', 'Delaware'), ('DC', 'District of Columbia'), ('FM', 'Federated States of Micronesia'), ('FL', 'Florida'), ('GA', 'Georgia'), ('GU', 'Guam'), ('HI', 'Hawaii'), ('ID', 'Idaho'), ('IL', 'Illinois'), ('IN', 'Indiana'), ('IA', 'Iowa'), ('KS', 'Kansas'), ('KY', 'Kentucky'), ('LA', 'Louisiana'), ('ME', 'Maine'), ('MH', 'Marshall Islands'), ('MD', 'Maryland'), ('MA', 'Massachusetts'), ('MI', 'Michigan'), ('MN', 'Minnesota'), ('MS', 'Mississippi'), ('MO', 'Missouri'), ('MT', 'Montana'), ('NE', 'Nebraska'), ('NV', 'Nevada'), ('NH', 'New Hampshire'), ('NJ', 'New Jersey'), ('NM', 'New Mexico'), ('NY', 'New York'), ('NC', 'North Carolina'), ('ND', 'North Dakota'), ('MP', 'Northern Mariana Islands'), ('OH', 'Ohio'), ('OK', 'Oklahoma'), ('OR', 'Oregon'), ('PW', 'Palau'), ('PA', 'Pennsylvania'), ('PR', 'Puerto Rico'), ('RI', 'Rhode Island'), ('SC', 'South Carolina'), ('SD', 'South Dakota'), ('TN', 'Tennessee'), ('TX', 'Texas'), ('UT', 'Utah'), ('VT', 'Vermont'), ('VI', 'Virgin Islands'), ('VA', 'Virginia'), ('WA', 'Washington'), ('WV', 'West Virginia'), ('WI', 'Wisconsin'), ('WY', 'Wyoming')])),
                ('zip_code', localflavor.us.models.USZipCodeField(help_text='The zip code for the organization, XXXXX or XXXXX-XXXX work.', max_length=10, db_index=True)),
            ],
        ),
        migrations.CreateModel(
            name='AttorneyOrganizationAssociation',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('attorney', models.ForeignKey(related_name='attorney_organization_associations', to='people_db.Attorney',
                                               on_delete=models.CASCADE)),
                ('attorney_organization', models.ForeignKey(related_name='attorney_organization_associations', to='people_db.AttorneyOrganization',
                                                            on_delete=models.CASCADE)),
                ('docket', models.ForeignKey(help_text='The docket that the attorney worked on while at this organization.', to='search.Docket',
                                             on_delete=models.CASCADE)),
            ],
        ),
        migrations.CreateModel(
            name='Party',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('date_created', models.DateTimeField(help_text='The time when this item was created', auto_now_add=True, db_index=True)),
                ('date_modified', models.DateTimeField(help_text='The last moment when the item was modified.', auto_now=True, db_index=True)),
                ('name', models.TextField(help_text='The name of the party.', db_index=True)),
                ('extra_info', models.TextField(help_text='Additional info from PACER', db_index=True)),
            ],
            options={
                'verbose_name_plural': 'Parties',
            },
        ),
        migrations.CreateModel(
            name='PartyType',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('name', models.CharField(help_text='The name of the type (Defendant, Plaintiff, etc.)', max_length=100, db_index=True)),
                ('docket', models.ForeignKey(related_name='party_types', to='search.Docket',
                                             on_delete=models.CASCADE)),
                ('party', models.ForeignKey(related_name='party_types', to='people_db.Party',
                                            on_delete=models.CASCADE)),
            ],
        ),
        migrations.CreateModel(
            name='Role',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('role', models.SmallIntegerField(help_text="The name of the attorney's role.", db_index=True, choices=[(1, 'Attorney to be noticed'), (2, 'Lead attorney'), (3, 'Attorney in sealed group'), (4, 'Pro hac vice'), (5, 'Self-terminated'), (6, 'Terminated'), (7, 'Suspended'), (8, 'Inactive'), (9, 'Disbarred')])),
                ('date_action', models.DateField(help_text='The date the attorney was disbarred, suspended, terminated...', null=True)),
                ('attorney', models.ForeignKey(related_name='roles', to='people_db.Attorney',
                                               on_delete=models.CASCADE)),
                ('docket', models.ForeignKey(help_text='The attorney represented the party on this docket in this role.', to='search.Docket',
                                             on_delete=models.CASCADE)),
                ('party', models.ForeignKey(related_name='roles', to='people_db.Party',
                                            on_delete=models.CASCADE)),
            ],
        ),
        migrations.AddField(
            model_name='party',
            name='attorneys',
            field=models.ManyToManyField(help_text='The attorneys involved with the party.', related_name='parties', through='people_db.Role', to='people_db.Attorney'),
        ),
        migrations.AlterUniqueTogether(
            name='attorneyorganization',
            unique_together=set([('name', 'address1', 'address2', 'city', 'state', 'zip_code')]),
        ),
        migrations.AddField(
            model_name='attorney',
            name='organizations',
            field=models.ManyToManyField(help_text='The organizations that the attorney is affiliated with', related_name='attorneys', through='people_db.AttorneyOrganizationAssociation', to='people_db.AttorneyOrganization'),
        ),
        migrations.AlterUniqueTogether(
            name='role',
            unique_together=set([('party', 'attorney', 'role')]),
        ),
        migrations.AlterUniqueTogether(
            name='partytype',
            unique_together=set([('docket', 'party', 'name')]),
        ),
        migrations.AlterUniqueTogether(
            name='party',
            unique_together=set([('name', 'extra_info')]),
        ),
        migrations.AlterUniqueTogether(
            name='attorneyorganizationassociation',
            unique_together=set([('attorney', 'attorney_organization', 'docket')]),
        ),
        migrations.AlterUniqueTogether(
            name='attorney',
            unique_together=set([('name', 'contact_raw')]),
        ),
    ]
