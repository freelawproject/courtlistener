# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('people_db', '0036_remove_unique_constraint_on_party_name'),
    ]

    operations = [
        migrations.CreateModel(
            name='CriminalComplaint',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('name', models.TextField(help_text=b"The name of the criminal complaint, for example, '8:1326 Reentry of Deported Alien'")),
                ('disposition', models.TextField(help_text=b'The disposition of the criminal complaint.')),
            ],
        ),
        migrations.CreateModel(
            name='CriminalCount',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('name', models.TextField(help_text=b"The name of the count, such as '21:952 and 960 - Importation of Marijuana(1)'.")),
                ('disposition', models.TextField(help_text=b"The disposition of the count, such as 'Custody of BOP for 60 months, followed by 4 years supervised release. No fine. $100 penalty assessment.", blank=True)),
                ('status', models.SmallIntegerField(help_text=b'Whether the count is pending or terminated.', choices=[(1, b'Pending'), (2, b'Terminated')])),
            ],
        ),
        migrations.AddField(
            model_name='partytype',
            name='highest_offense_level_opening',
            field=models.TextField(help_text=b'In a criminal case, the highest offense level at the opening of the case.', blank=True),
        ),
        migrations.AddField(
            model_name='partytype',
            name='highest_offense_level_terminated',
            field=models.TextField(help_text=b'In a criminal case, the highest offense level at the end of the case.', blank=True),
        ),
        migrations.AddField(
            model_name='criminalcount',
            name='party_type',
            field=models.ForeignKey(related_name='criminal_counts', to='people_db.PartyType', help_text=b'The docket and party the counts are associated with.'),
        ),
        migrations.AddField(
            model_name='criminalcomplaint',
            name='party_type',
            field=models.ForeignKey(related_name='criminal_complaints', to='people_db.PartyType', help_text=b'The docket and party the complaints are associated with.'),
        ),
    ]
