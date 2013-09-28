from alert.alerts.models import Alert
from alert.donate.models import Donation
from alert.favorites.models import Favorite
from django.db import models
from django.contrib.auth.models import User
from localflavor.us.models import USStateField


class BarMembership(models.Model):
    barMembershipUUID = models.AutoField(
        'a unique ID for each bar membership',
        primary_key=True
    )
    barMembership = USStateField(
        'the two letter state abbreviation of a bar membership'
    )

    def __unicode__(self):
        return self.get_barMembership_display()

    class Meta:
        verbose_name = 'bar membership'
        db_table = 'BarMembership'
        ordering = ['barMembership']


class UserProfile(models.Model):
    userProfileUUID = models.AutoField(
        'a unique ID for each user profile',
        primary_key=True
    )
    user = models.OneToOneField(
        User,
        related_name='profile',
        verbose_name='the user this model extends',
        unique=True
    )
    stub_account = models.BooleanField(
        default=False,
    )
    employer = models.CharField(
        'the user\'s employer',
        max_length=100,
        blank=True,
        null=True,
    )
    address1 = models.CharField(
        max_length=100,
        blank=True,
        null=True,
    )
    address2 = models.CharField(
        max_length=100,
        blank=True,
        null=True,
    )
    city = models.CharField(
        max_length=50,
        blank=True,
        null=True,
    )
    state = models.CharField(
        max_length=2,
        blank=True,
        null=True,
    )
    zip_code = models.CharField(
        max_length=10,
        blank=True,
        null=True,
    )
    avatar = models.ImageField(
        'the user\'s avatar',
        upload_to='avatars/%Y/%m/%d',
        blank=True
    )
    wants_newsletter = models.BooleanField(
        'This user wants newsletters',
        default=False
    )
    barmembership = models.ManyToManyField(
        BarMembership,
        verbose_name='the bar memberships held by the user',
        blank=True,
        null=True
    )
    alert = models.ManyToManyField(
        Alert,
        verbose_name='the alerts created by the user',
        blank=True,
        null=True
    )
    donation = models.ManyToManyField(
        Donation,
        verbose_name='the donations made by the user',
        blank=True,
        null=True
    )
    favorite = models.ManyToManyField(
        Favorite,
        verbose_name='the favorites created by the user',
        related_name='users',
        blank=True,
        null=True
    )
    plaintext_preferred = models.BooleanField(
        'should the alert should be sent in plaintext',
        default=False
    )
    activation_key = models.CharField(
        max_length=40
    )
    key_expires = models.DateTimeField(
        'The time and date when the user\'s activation_key expires',
        blank=True,
        null=True
    )
    email_confirmed = models.BooleanField(
        'The user has confirmed their email address',
        default=False
    )

    def __unicode__(self):
        return self.user.username

    class Meta:
        verbose_name = 'user profile'
        verbose_name_plural = 'user profiles'
        db_table = 'UserProfile'
