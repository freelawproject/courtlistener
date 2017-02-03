# -*- coding: utf-8 -*-
from __future__ import unicode_literals

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
                ('date_created', models.DateTimeField(help_text=b'The time when this item was created', auto_now_add=True, db_index=True)),
                ('date_modified', models.DateTimeField(help_text=b'The last moment when the item was modified.', auto_now=True, db_index=True)),
                ('name', models.TextField(help_text=b'The name of the attorney.', db_index=True)),
                ('contact_raw', models.TextField(help_text=b'The raw contents of the contact field', db_index=True)),
                ('phone', localflavor.us.models.PhoneNumberField(help_text=b'The phone number of the attorney.', max_length=20)),
                ('fax', localflavor.us.models.PhoneNumberField(help_text=b'The fax number of the attorney.', max_length=20)),
                ('email', models.EmailField(help_text=b'The email address of the attorney.', max_length=254)),
            ],
        ),
        migrations.CreateModel(
            name='AttorneyOrganization',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('date_created', models.DateTimeField(help_text=b'The time when this item was created', auto_now_add=True, db_index=True)),
                ('date_modified', models.DateTimeField(help_text=b'The last moment when the item was modified.', auto_now=True, db_index=True)),
                ('name', models.TextField(help_text=b'The name of the organization.', db_index=True)),
                ('address1', models.TextField(help_text=b'The normalized address1 of the organization', db_index=True)),
                ('address2', models.TextField(help_text=b'The normalized address2 of the organization', db_index=True)),
                ('city', models.TextField(help_text=b'The normalized city of the organization', db_index=True)),
                ('state', localflavor.us.models.USPostalCodeField(help_text=b'The two-letter USPS postal abbreviation for the organization', max_length=2, db_index=True, choices=[(b'AL', b'Alabama'), (b'AK', b'Alaska'), (b'AS', b'American Samoa'), (b'AZ', b'Arizona'), (b'AR', b'Arkansas'), (b'AA', b'Armed Forces Americas'), (b'AE', b'Armed Forces Europe'), (b'AP', b'Armed Forces Pacific'), (b'CA', b'California'), (b'CO', b'Colorado'), (b'CT', b'Connecticut'), (b'DE', b'Delaware'), (b'DC', b'District of Columbia'), (b'FM', b'Federated States of Micronesia'), (b'FL', b'Florida'), (b'GA', b'Georgia'), (b'GU', b'Guam'), (b'HI', b'Hawaii'), (b'ID', b'Idaho'), (b'IL', b'Illinois'), (b'IN', b'Indiana'), (b'IA', b'Iowa'), (b'KS', b'Kansas'), (b'KY', b'Kentucky'), (b'LA', b'Louisiana'), (b'ME', b'Maine'), (b'MH', b'Marshall Islands'), (b'MD', b'Maryland'), (b'MA', b'Massachusetts'), (b'MI', b'Michigan'), (b'MN', b'Minnesota'), (b'MS', b'Mississippi'), (b'MO', b'Missouri'), (b'MT', b'Montana'), (b'NE', b'Nebraska'), (b'NV', b'Nevada'), (b'NH', b'New Hampshire'), (b'NJ', b'New Jersey'), (b'NM', b'New Mexico'), (b'NY', b'New York'), (b'NC', b'North Carolina'), (b'ND', b'North Dakota'), (b'MP', b'Northern Mariana Islands'), (b'OH', b'Ohio'), (b'OK', b'Oklahoma'), (b'OR', b'Oregon'), (b'PW', b'Palau'), (b'PA', b'Pennsylvania'), (b'PR', b'Puerto Rico'), (b'RI', b'Rhode Island'), (b'SC', b'South Carolina'), (b'SD', b'South Dakota'), (b'TN', b'Tennessee'), (b'TX', b'Texas'), (b'UT', b'Utah'), (b'VT', b'Vermont'), (b'VI', b'Virgin Islands'), (b'VA', b'Virginia'), (b'WA', b'Washington'), (b'WV', b'West Virginia'), (b'WI', b'Wisconsin'), (b'WY', b'Wyoming')])),
                ('zip_code', localflavor.us.models.USZipCodeField(help_text=b'The zip code for the organization, XXXXX or XXXXX-XXXX work.', max_length=10, db_index=True)),
            ],
        ),
        migrations.CreateModel(
            name='Party',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('date_created', models.DateTimeField(help_text=b'The time when this item was created', auto_now_add=True, db_index=True)),
                ('date_modified', models.DateTimeField(help_text=b'The last moment when the item was modified.', auto_now=True, db_index=True)),
                ('name', models.TextField(help_text=b'The name of the party.', db_index=True)),
                ('extra_info', models.TextField(help_text=b'Additional info from PACER', db_index=True)),
            ],
        ),
        migrations.CreateModel(
            name='PartyType',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('name', models.CharField(help_text=b'The name of the type (Defendant, Plaintiff, etc.)', max_length=b'100', db_index=True)),
                ('docket', models.ForeignKey(related_name='party_types', to='search.Docket')),
                ('party', models.ForeignKey(related_name='party_types', to='people_db.Party')),
            ],
        ),
        migrations.CreateModel(
            name='Role',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('role', models.SmallIntegerField(help_text=b"The name of the attorney's role.", db_index=True, choices=[(1, b'Attorney to be noticed'), (2, b'Lead Attorney'), (3, b'Attorney in sealed group'), (4, b'Pro hac vice'), (5, b'Self-terminated'), (6, b'Terminated'), (7, b'Suspended'), (8, b'Inactive'), (9, b'Disbarred')])),
                ('attorney', models.ForeignKey(related_name='roles', to='people_db.Attorney')),
                ('party', models.ForeignKey(related_name='roles', to='people_db.Party')),
            ],
        ),
        migrations.AddField(
            model_name='party',
            name='attorneys',
            field=models.ManyToManyField(help_text=b'The attorneys involved with the party.', related_name='parties', through='people_db.Role', to='people_db.Attorney'),
        ),
        migrations.AlterUniqueTogether(
            name='attorneyorganization',
            unique_together=set([('name', 'address1', 'address2', 'city', 'state', 'zip_code')]),
        ),
        migrations.AddField(
            model_name='attorney',
            name='organizations',
            field=models.ManyToManyField(help_text=b'The organizations that the attorney is affiliated with', related_name='attorneys', to='people_db.AttorneyOrganization'),
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
            name='attorney',
            unique_together=set([('name', 'contact_raw')]),
        ),
    ]
