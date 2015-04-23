# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import localflavor.us.models
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        ('alerts', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('donate', '0001_initial'),
        ('favorites', '0002_favorite_cluster_id'),
    ]

    operations = [
        migrations.CreateModel(
            name='BarMembership',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('barMembership', localflavor.us.models.USStateField(max_length=2, verbose_name=b'the two letter state abbreviation of a bar membership', choices=[(b'AL', b'Alabama'), (b'AK', b'Alaska'), (b'AS', b'American Samoa'), (b'AZ', b'Arizona'), (b'AR', b'Arkansas'), (b'AA', b'Armed Forces Americas'), (b'AE', b'Armed Forces Europe'), (b'AP', b'Armed Forces Pacific'), (b'CA', b'California'), (b'CO', b'Colorado'), (b'CT', b'Connecticut'), (b'DE', b'Delaware'), (b'DC', b'District of Columbia'), (b'FL', b'Florida'), (b'GA', b'Georgia'), (b'GU', b'Guam'), (b'HI', b'Hawaii'), (b'ID', b'Idaho'), (b'IL', b'Illinois'), (b'IN', b'Indiana'), (b'IA', b'Iowa'), (b'KS', b'Kansas'), (b'KY', b'Kentucky'), (b'LA', b'Louisiana'), (b'ME', b'Maine'), (b'MD', b'Maryland'), (b'MA', b'Massachusetts'), (b'MI', b'Michigan'), (b'MN', b'Minnesota'), (b'MS', b'Mississippi'), (b'MO', b'Missouri'), (b'MT', b'Montana'), (b'NE', b'Nebraska'), (b'NV', b'Nevada'), (b'NH', b'New Hampshire'), (b'NJ', b'New Jersey'), (b'NM', b'New Mexico'), (b'NY', b'New York'), (b'NC', b'North Carolina'), (b'ND', b'North Dakota'), (b'MP', b'Northern Mariana Islands'), (b'OH', b'Ohio'), (b'OK', b'Oklahoma'), (b'OR', b'Oregon'), (b'PA', b'Pennsylvania'), (b'PR', b'Puerto Rico'), (b'RI', b'Rhode Island'), (b'SC', b'South Carolina'), (b'SD', b'South Dakota'), (b'TN', b'Tennessee'), (b'TX', b'Texas'), (b'UT', b'Utah'), (b'VT', b'Vermont'), (b'VI', b'Virgin Islands'), (b'VA', b'Virginia'), (b'WA', b'Washington'), (b'WV', b'West Virginia'), (b'WI', b'Wisconsin'), (b'WY', b'Wyoming')])),
            ],
            options={
                'ordering': ['barMembership'],
                'verbose_name': 'bar membership',
            },
        ),
        migrations.CreateModel(
            name='UserProfile',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('stub_account', models.BooleanField(default=False)),
                ('employer', models.CharField(max_length=100, null=True, verbose_name=b"the user's employer", blank=True)),
                ('address1', models.CharField(max_length=100, null=True, blank=True)),
                ('address2', models.CharField(max_length=100, null=True, blank=True)),
                ('city', models.CharField(max_length=50, null=True, blank=True)),
                ('state', models.CharField(max_length=2, null=True, blank=True)),
                ('zip_code', models.CharField(max_length=10, null=True, blank=True)),
                ('avatar', models.ImageField(upload_to=b'avatars/%Y/%m/%d', verbose_name=b"the user's avatar", blank=True)),
                ('wants_newsletter', models.BooleanField(default=False, verbose_name=b'This user wants newsletters')),
                ('plaintext_preferred', models.BooleanField(default=False, verbose_name=b'should the alert should be sent in plaintext')),
                ('activation_key', models.CharField(max_length=40)),
                ('key_expires', models.DateTimeField(null=True, verbose_name=b"The time and date when the user's activation_key expires", blank=True)),
                ('email_confirmed', models.BooleanField(default=False, verbose_name=b'The user has confirmed their email address')),
                ('alert', models.ManyToManyField(to='alerts.Alert', verbose_name=b'the alerts created by the user', blank=True)),
                ('barmembership', models.ManyToManyField(to='users.BarMembership', verbose_name=b'the bar memberships held by the user', blank=True)),
                ('donation', models.ManyToManyField(related_name='donors', verbose_name=b'the donations made by the user', to='donate.Donation', blank=True)),
                ('favorite', models.ManyToManyField(related_name='users', verbose_name=b'the favorites created by the user', to='favorites.Favorite', blank=True)),
                ('user', models.OneToOneField(related_name='profile', verbose_name=b'the user this model extends', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'user profile',
                'verbose_name_plural': 'user profiles',
            },
        ),
    ]
