# -*- coding: utf-8 -*-


from django.db import models, migrations
import localflavor.us.models
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='BarMembership',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('barMembership', localflavor.us.models.USStateField(max_length=2, verbose_name='the two letter state abbreviation of a bar membership', choices=[('AL', 'Alabama'), ('AK', 'Alaska'), ('AS', 'American Samoa'), ('AZ', 'Arizona'), ('AR', 'Arkansas'), ('AA', 'Armed Forces Americas'), ('AE', 'Armed Forces Europe'), ('AP', 'Armed Forces Pacific'), ('CA', 'California'), ('CO', 'Colorado'), ('CT', 'Connecticut'), ('DE', 'Delaware'), ('DC', 'District of Columbia'), ('FL', 'Florida'), ('GA', 'Georgia'), ('GU', 'Guam'), ('HI', 'Hawaii'), ('ID', 'Idaho'), ('IL', 'Illinois'), ('IN', 'Indiana'), ('IA', 'Iowa'), ('KS', 'Kansas'), ('KY', 'Kentucky'), ('LA', 'Louisiana'), ('ME', 'Maine'), ('MD', 'Maryland'), ('MA', 'Massachusetts'), ('MI', 'Michigan'), ('MN', 'Minnesota'), ('MS', 'Mississippi'), ('MO', 'Missouri'), ('MT', 'Montana'), ('NE', 'Nebraska'), ('NV', 'Nevada'), ('NH', 'New Hampshire'), ('NJ', 'New Jersey'), ('NM', 'New Mexico'), ('NY', 'New York'), ('NC', 'North Carolina'), ('ND', 'North Dakota'), ('MP', 'Northern Mariana Islands'), ('OH', 'Ohio'), ('OK', 'Oklahoma'), ('OR', 'Oregon'), ('PA', 'Pennsylvania'), ('PR', 'Puerto Rico'), ('RI', 'Rhode Island'), ('SC', 'South Carolina'), ('SD', 'South Dakota'), ('TN', 'Tennessee'), ('TX', 'Texas'), ('UT', 'Utah'), ('VT', 'Vermont'), ('VI', 'Virgin Islands'), ('VA', 'Virginia'), ('WA', 'Washington'), ('WV', 'West Virginia'), ('WI', 'Wisconsin'), ('WY', 'Wyoming')])),
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
                ('employer', models.CharField(max_length=100, null=True, verbose_name="the user's employer", blank=True)),
                ('address1', models.CharField(max_length=100, null=True, blank=True)),
                ('address2', models.CharField(max_length=100, null=True, blank=True)),
                ('city', models.CharField(max_length=50, null=True, blank=True)),
                ('state', models.CharField(max_length=2, null=True, blank=True)),
                ('zip_code', models.CharField(max_length=10, null=True, blank=True)),
                ('avatar', models.ImageField(upload_to='avatars/%Y/%m/%d', verbose_name="the user's avatar", blank=True)),
                ('wants_newsletter', models.BooleanField(default=False, verbose_name='This user wants newsletters')),
                ('plaintext_preferred', models.BooleanField(default=False, verbose_name='should the alert should be sent in plaintext')),
                ('activation_key', models.CharField(max_length=40)),
                ('key_expires', models.DateTimeField(null=True, verbose_name="The time and date when the user's activation_key expires", blank=True)),
                ('email_confirmed', models.BooleanField(default=False, verbose_name='The user has confirmed their email address')),
                ('barmembership', models.ManyToManyField(to='users.BarMembership', verbose_name='the bar memberships held by the user', blank=True)),
                ('user', models.OneToOneField(related_name='profile', verbose_name='the user this model extends', to=settings.AUTH_USER_MODEL,
                                              on_delete=models.CASCADE)),
            ],
            options={
                'verbose_name': 'user profile',
                'verbose_name_plural': 'user profiles',
            },
        ),
    ]
