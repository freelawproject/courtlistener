# Generated by Django 3.1.7 on 2021-05-28 19:34

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('people_db', '0001_initial'),
        ('search', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='role',
            name='docket',
            field=models.ForeignKey(help_text='The attorney represented the party on this docket in this role.', on_delete=django.db.models.deletion.CASCADE, to='search.docket'),
        ),
        migrations.AddField(
            model_name='role',
            name='party',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='roles', to='people_db.party'),
        ),
        migrations.AddField(
            model_name='retentionevent',
            name='position',
            field=models.ForeignKey(blank=True, help_text='The position that was retained by this event.', null=True, on_delete=django.db.models.deletion.CASCADE, related_name='retention_events', to='people_db.position'),
        ),
        migrations.AddField(
            model_name='position',
            name='appointer',
            field=models.ForeignKey(blank=True, help_text='If this is an appointed position, the person-position responsible for the appointment. This field references other positions instead of referencing people because that allows you to know the position a person held when an appointment was made.', null=True, on_delete=django.db.models.deletion.CASCADE, related_name='appointed_positions', to='people_db.position'),
        ),
        migrations.AddField(
            model_name='position',
            name='court',
            field=models.ForeignKey(blank=True, help_text='If this was a judicial position, this is the jurisdiction where it was held.', null=True, on_delete=django.db.models.deletion.CASCADE, related_name='court_positions', to='search.court'),
        ),
        migrations.AddField(
            model_name='position',
            name='person',
            field=models.ForeignKey(blank=True, help_text='The person that held the position.', null=True, on_delete=django.db.models.deletion.CASCADE, related_name='positions', to='people_db.person'),
        ),
        migrations.AddField(
            model_name='position',
            name='predecessor',
            field=models.ForeignKey(blank=True, help_text='The person that previously held this position', null=True, on_delete=django.db.models.deletion.CASCADE, to='people_db.person'),
        ),
        migrations.AddField(
            model_name='position',
            name='school',
            field=models.ForeignKey(blank=True, help_text='If this was an academic job, this is the school where the person worked.', null=True, on_delete=django.db.models.deletion.CASCADE, to='people_db.school'),
        ),
        migrations.AddField(
            model_name='position',
            name='supervisor',
            field=models.ForeignKey(blank=True, help_text='If this is a clerkship, the supervising judge.', null=True, on_delete=django.db.models.deletion.CASCADE, related_name='supervised_positions', to='people_db.person'),
        ),
        migrations.AddField(
            model_name='politicalaffiliation',
            name='person',
            field=models.ForeignKey(blank=True, help_text='The person with the political affiliation', null=True, on_delete=django.db.models.deletion.CASCADE, related_name='political_affiliations', to='people_db.person'),
        ),
        migrations.AddField(
            model_name='person',
            name='is_alias_of',
            field=models.ForeignKey(blank=True, help_text='Any nicknames or other aliases that a person has. For example, William Jefferson Clinton has an alias to Bill', null=True, on_delete=django.db.models.deletion.CASCADE, related_name='aliases', to='people_db.person'),
        ),
        migrations.AddField(
            model_name='person',
            name='race',
            field=models.ManyToManyField(blank=True, help_text="A person's race or races if they are multi-racial.", to='people_db.Race'),
        ),
        migrations.AddField(
            model_name='partytype',
            name='docket',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='party_types', to='search.docket'),
        ),
        migrations.AddField(
            model_name='partytype',
            name='party',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='party_types', to='people_db.party'),
        ),
        migrations.AddField(
            model_name='party',
            name='attorneys',
            field=models.ManyToManyField(help_text='The attorneys involved with the party.', related_name='parties', through='people_db.Role', to='people_db.Attorney'),
        ),
        migrations.AddField(
            model_name='education',
            name='person',
            field=models.ForeignKey(blank=True, help_text='The person that completed this education', null=True, on_delete=django.db.models.deletion.CASCADE, related_name='educations', to='people_db.person'),
        ),
        migrations.AddField(
            model_name='education',
            name='school',
            field=models.ForeignKey(help_text='The school where this education was compeleted', on_delete=django.db.models.deletion.CASCADE, related_name='educations', to='people_db.school'),
        ),
        migrations.AddField(
            model_name='criminalcount',
            name='party_type',
            field=models.ForeignKey(help_text='The docket and party the counts are associated with.', on_delete=django.db.models.deletion.CASCADE, related_name='criminal_counts', to='people_db.partytype'),
        ),
        migrations.AddField(
            model_name='criminalcomplaint',
            name='party_type',
            field=models.ForeignKey(help_text='The docket and party the complaints are associated with.', on_delete=django.db.models.deletion.CASCADE, related_name='criminal_complaints', to='people_db.partytype'),
        ),
        migrations.AddField(
            model_name='attorneyorganizationassociation',
            name='attorney',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='attorney_organization_associations', to='people_db.attorney'),
        ),
        migrations.AddField(
            model_name='attorneyorganizationassociation',
            name='attorney_organization',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='attorney_organization_associations', to='people_db.attorneyorganization'),
        ),
        migrations.AddField(
            model_name='attorneyorganizationassociation',
            name='docket',
            field=models.ForeignKey(help_text='The docket that the attorney worked on while at this organization.', on_delete=django.db.models.deletion.CASCADE, to='search.docket'),
        ),
        migrations.AlterUniqueTogether(
            name='attorneyorganization',
            unique_together={('name', 'address1', 'address2', 'city', 'state', 'zip_code')},
        ),
        migrations.AddField(
            model_name='attorney',
            name='organizations',
            field=models.ManyToManyField(help_text='The organizations that the attorney is affiliated with', related_name='attorneys', through='people_db.AttorneyOrganizationAssociation', to='people_db.AttorneyOrganization'),
        ),
        migrations.AddField(
            model_name='abarating',
            name='person',
            field=models.ForeignKey(blank=True, help_text='The person rated by the American Bar Association', null=True, on_delete=django.db.models.deletion.CASCADE, related_name='aba_ratings', to='people_db.person'),
        ),
        migrations.AlterUniqueTogether(
            name='role',
            unique_together={('party', 'attorney', 'role', 'docket', 'date_action')},
        ),
        migrations.AlterUniqueTogether(
            name='partytype',
            unique_together={('docket', 'party', 'name')},
        ),
        migrations.AlterUniqueTogether(
            name='attorneyorganizationassociation',
            unique_together={('attorney', 'attorney_organization', 'docket')},
        ),
    ]
